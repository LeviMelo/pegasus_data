# Releasing `pegasus-data`

The release artifact is the product. A passing repository test suite does not
prove that a wheel contains Pegasus's SQL schema, reviewed curation, source map
and compiled semantic packs, so every release must pass the archive and
clean-install checks below.

## Version policy

`pyproject.toml` is the only version literal. Installed code reports that value
through `importlib.metadata`. Use PEP 440 versions; the first external candidate
is `0.1.0a1`, followed by later prereleases if the installed artifact exposes a
defect, and `0.1.0` when it is ready to be promoted.

PyPI versions are immutable. Bump the version before rebuilding a changed
artifact, commit the bump, and tag that exact commit as `vX.Y.Z`.

## Build and inspect

Use Python 3.11 or newer from a clean checkout:

```powershell
python -m pip install --upgrade build twine
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python -m build
python -m twine check dist\*
python scripts\verify_distribution.py --expected-version 0.1.0a1 dist\*
```

The verifier compares package data in both archives with
`src/pegasus_data`, validates every manifest size and SHA-256 digest, checks the
CLI entry point and license, rejects local databases/caches, and requires the
wheel and sdist to report the same version.

## Clean-room acceptance test

Do not run the smoke test with the checkout's Python path. Install the built
wheel into a new environment and change to a directory outside the repository:

```powershell
$wheel = (Get-ChildItem dist\*.whl | Select-Object -First 1).FullName
$venv = Join-Path $env:TEMP "pegasus-wheel-test"
Remove-Item -Recurse -Force $venv -ErrorAction SilentlyContinue
py -m venv $venv
& "$venv\Scripts\python.exe" -m pip install --upgrade pip
& "$venv\Scripts\python.exe" -m pip install $wheel

Push-Location $env:TEMP
& "$venv\Scripts\python.exe" `
  "C:\path\to\pegasus_data\scripts\smoke_installed.py" `
  --forbid-root "C:\path\to\pegasus_data"
& "$venv\Scripts\pegasus-data.exe" --help
Pop-Location
```

The smoke test verifies the import came from the isolated environment, checks
the runtime version, schema, curation and all manifest resources, and plans an
offline `SIH-RD` query from the shipped control plane. It does not download fact
data.

Also prove that the sdist can be rebuilt independently: extract it outside the
checkout, run `python -m build --wheel` in the extracted directory, and verify
that rebuilt wheel with the same script.

## Publish

The GitHub `publish` workflow rebuilds and rechecks the distributions when a
GitHub release is published, requires the tag to match the artifact version,
then publishes with PyPI Trusted Publishing. Before the first release, a PyPI
project owner must configure a trusted publisher for this repository, workflow
`publish.yml`, environment `pypi`.

For a one-off rehearsal, upload a never-before-used prerelease version to
TestPyPI:

```powershell
python -m twine upload --repository testpypi dist\*
```

Do not upload from a dirty tree or reuse a version after changing an artifact.
Publishing changes external state and is deliberately not part of the local
release script.
