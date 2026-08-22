"""Freshness is a stated policy, and staging is safe between processes.

A warm fetch deliberately avoids the network, so "current" has always meant
*current according to the last crawl*, never *current on DATASUS now*. That is
a defensible reproducibility policy and was an unstated one — which matters
because this project explicitly treats republication under the same pathname as
a real possibility.

Staging was named from the source path, so two processes fetching the same file
shared one partial: each resumed from the other's offset and one finalised bytes
the other had half-written. No amount of worker locking helps; the other process
is not in this interpreter.
"""

from __future__ import annotations

import pytest

from pegasus_data.acquire.cache import BlobStore
from pegasus_data.acquire.fetcher import REFRESH_POLICIES, Fetcher, FetchResult
from pegasus_data.catalog.store import Catalog


@pytest.fixture
def store(tmp_path):
    catalog = Catalog(tmp_path / "c.sqlite")
    blobs = BlobStore(tmp_path / "blobs", catalog)
    yield catalog, blobs
    catalog.close()


def _stored(catalog, blobs, path, *, remote_size, listed_size):
    digest = blobs.put_bytes(b"x" * remote_size, source_path=path, remote_size=remote_size)
    catalog.upsert_files(
        [{"path": path, "directory": "/d", "filename": path.rsplit("/", 1)[1],
          "extension": ".dbc", "size": listed_size}]
    )
    return digest


class TestTheFreshnessPolicyIsExplicit:
    def test_the_policies_are_named_and_described(self):
        assert set(REFRESH_POLICIES) == {"catalog", "never", "remote"}
        assert all(REFRESH_POLICIES.values()), "each needs a description a user can read"

    def test_an_unknown_policy_is_refused_at_construction(self, store):
        catalog, blobs = store
        with pytest.raises(ValueError, match="unknown refresh policy"):
            Fetcher(catalog, blobs, host="example.invalid", refresh="sometimes")

    def test_catalog_is_the_default_and_notices_a_changed_listing(self, store):
        """A republication the last crawl DID see must not be served from cache."""
        catalog, blobs = store
        _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=999)
        fetcher = Fetcher(catalog, blobs, host="example.invalid")
        assert fetcher.refresh == "catalog"
        assert fetcher._should_skip("/p/a.dbc") is None

    def test_never_serves_the_stored_copy_even_when_known_stale(self, store):
        """Reproducibility over currency, stated outright."""
        catalog, blobs = store
        digest = _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=999)
        fetcher = Fetcher(catalog, blobs, host="example.invalid", refresh="never")
        assert fetcher._should_skip("/p/a.dbc") == digest

    def test_remote_asks_the_server_and_refetches_on_a_change(self, store):
        catalog, blobs = store
        _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=100)
        fetcher = Fetcher(catalog, blobs, host="example.invalid", refresh="remote")

        class _Client:
            def stat(self, path):
                return 4242, None  # the server says it changed

        assert fetcher._should_skip("/p/a.dbc", client=_Client()) is None

    def test_remote_keeps_the_copy_when_the_server_agrees(self, store):
        catalog, blobs = store
        digest = _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=100)
        fetcher = Fetcher(catalog, blobs, host="example.invalid", refresh="remote")

        class _Client:
            def stat(self, path):
                return 100, None

        assert fetcher._should_skip("/p/a.dbc", client=_Client()) == digest

    def test_an_unreachable_server_is_not_proof_of_change(self, store):
        """Falling back to the catalog beats refetching everything on a blip."""
        catalog, blobs = store
        digest = _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=100)
        fetcher = Fetcher(catalog, blobs, host="example.invalid", refresh="remote")

        class _Client:
            def stat(self, path):
                raise OSError("connection reset")

        assert fetcher._should_skip("/p/a.dbc", client=_Client()) == digest

    def test_remote_does_not_pre_settle_from_cache(self, store):
        """Pre-settling happens before any socket exists, so asking the server
        there is impossible; each worker re-checks with its own client."""
        catalog, blobs = store
        _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=100)
        fetcher = Fetcher(catalog, blobs, host="example.invalid", refresh="remote")

        class _Stats:
            skipped = 0
            bytes_from_cache = 0

        pending = fetcher._settle_from_cache(
            ["/p/a.dbc"], force=False, stats=_Stats(), emit=lambda r: None
        )
        assert pending == ["/p/a.dbc"]


class TestStagingIsSafeBetweenProcesses:
    def test_two_acquisitions_of_one_source_do_not_share_a_partial(self, store):
        _catalog, blobs = store
        first = blobs.staging_path("/p/big.dbc")
        second = blobs.staging_path("/p/big.dbc")
        assert first != second, (
            "a name derived from the source made two processes append into one file"
        )

    def test_staging_stays_on_the_stores_filesystem(self, store):
        """os.replace is only atomic within one filesystem."""
        _catalog, blobs = store
        assert blobs.root in blobs.staging_path("/p/big.dbc").parents

    def test_adoption_refuses_a_staged_file_of_the_wrong_length(self, store):
        _catalog, blobs = store
        staged = blobs.staging_path("/p/big.dbc")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"short")
        with pytest.raises(OSError, match="refusing to adopt"):
            blobs.adopt(staged, "a" * 64, 999, source_path="/p/big.dbc")
        assert not staged.exists(), "the mismatched partial was left behind"

    def test_adoption_accepts_a_staged_file_of_the_right_length(self, store):
        _catalog, blobs = store
        staged = blobs.staging_path("/p/big.dbc")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"12345")
        digest = "b" * 64
        assert blobs.adopt(staged, digest, 5, source_path="/p/big.dbc") == digest
        assert blobs.path_for(digest).read_bytes() == b"12345"

    def test_abandoned_partials_can_be_reclaimed(self, store):
        """Unique names mean a killed process leaves its partial with nothing
        to reuse it; the deterministic name at least got overwritten."""
        import os
        import time

        _catalog, blobs = store
        old = blobs.staging_path("/p/dead.dbc")
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b"abandoned")
        os.utime(old, (time.time() - 200_000, time.time() - 200_000))
        fresh = blobs.staging_path("/p/live.dbc")
        fresh.write_bytes(b"in flight")

        assert blobs.sweep_staging() == 1
        assert not old.exists()
        assert fresh.exists(), "a partial being written right now must not be swept"


class TestFetchOneAnswersFromCache:
    def test_it_does_not_dial_for_a_file_already_stored(self, store, monkeypatch):
        """fetch_many() learned this and fetch_one() did not, so the single-file
        door failed outright when the server was unreachable — for a request
        that needed no server."""
        catalog, blobs = store
        digest = _stored(catalog, blobs, "/p/a.dbc", remote_size=100, listed_size=100)
        import pegasus_data.acquire.fetcher as mod

        def _explode(*a, **k):
            raise AssertionError("a connection was opened for a cached file")

        monkeypatch.setattr(mod, "FtpClient", _explode)
        fetcher = Fetcher(catalog, blobs, host="example.invalid")
        result = fetcher.fetch_one("/p/a.dbc")
        assert isinstance(result, FetchResult)
        assert result.skipped and result.sha256 == digest
