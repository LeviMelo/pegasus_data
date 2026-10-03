"""Settings as annotators: how each setting classifies the same persons (theory §2.2, §5; T4).

A categorical attribute a clerk records (race, the place of a death, the type
of delivery) is the *setting's* classification of the person, not an
observation of a self-declared truth. Once records are merged into persons
(``entities.py``), the same person is classified by several settings, which is
the design the Dawid–Skene model estimates:

- a latent class per person, ``z``, with prior ``π``;
- per setting ``s`` a confusion matrix ``θ_s[z, j] = P(setting s records j | z)``;
- persons are independent, and settings are independent given ``z``.

EM alternates the posterior of each person's class (E) with the priors and
confusion matrices (M), started from majority vote. The output is each
setting's matrix (how it classifies relative to the consensus), the consensus
prior, and each person's posterior. The consensus is what the settings agree
on, net of each one's tendency: under the premise that clerks classify, there
is no self-declared record to recover, and nothing here claims there is.

Identifiability needs settings that see the same persons; a person seen once
carries no information about the confusion and is left out. A setting's
matrix is reported with the number of persons behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pyarrow as pa


@dataclass
class AnnotatorModel:
    classes: list[str]
    settings: list[str]
    prior: np.ndarray                 # (K,)
    confusion: np.ndarray             # (S, K, K): confusion[s, z, j]
    persons: int
    observations_per_setting: np.ndarray
    iterations: int
    log_likelihood: float

    def summary(self) -> dict[str, Any]:
        return {
            "classes": self.classes,
            "persons": self.persons,
            "iterations": self.iterations,
            "log_likelihood": round(self.log_likelihood, 2),
            "consensus_prior": {c: round(float(p), 4) for c, p in zip(self.classes, self.prior, strict=True)},
            "settings": {
                s: {
                    "observations": int(self.observations_per_setting[i]),
                    "agrees_with_consensus": {
                        c: round(float(self.confusion[i, k, k]), 4) for k, c in enumerate(self.classes)
                    },
                    "confusion": {
                        c: {d: round(float(self.confusion[i, k, j]), 4) for j, d in enumerate(self.classes)}
                        for k, c in enumerate(self.classes)
                    },
                }
                for i, s in enumerate(self.settings)
            },
        }


def fit(observations: pa.Table, *, max_iter: int = 200, tol: float = 1e-7, smoothing: float = 0.5,
        groups: dict[str, str] | None = None, strength: float = 50.0) -> AnnotatorModel:
    """Dawid–Skene EM over ``observations`` with columns person, setting, label.

    Persons with a single observation are dropped (they inform no confusion).
    ``smoothing`` adds pseudo-counts to every confusion cell, so a setting that
    never recorded a class for some consensus class keeps a small probability.

    ``groups`` maps a setting to its group (a hospital to its system): each
    setting's confusion is then shrunk toward its group's pooled confusion by
    ``strength`` pseudo-observations per consensus class (hierarchical
    parameters, linkage-theory §2.3). A large hospital keeps its own matrix; a
    small one leans on its system's.
    """
    person = observations.column("person").to_numpy(zero_copy_only=False)
    setting = np.asarray(observations.column("setting").to_pylist(), dtype=object)
    label = np.asarray(observations.column("label").to_pylist(), dtype=object)
    keep = np.array([lb is not None for lb in label])
    person, setting, label = person[keep], setting[keep], label[keep]
    # Persons seen at least twice.
    uniq, inv, counts = np.unique(person, return_inverse=True, return_counts=True)
    multi = counts[inv] >= 2
    person, setting, label = person[multi], setting[multi], label[multi]
    classes = sorted(set(label.tolist()))
    settings = sorted(set(setting.tolist()))
    pid, p_inv = np.unique(person, return_inverse=True)
    s_idx = np.array([settings.index(x) for x in setting]) if len(setting) else np.zeros(0, int)
    c_index = {c: i for i, c in enumerate(classes)}
    j_idx = np.array([c_index[x] for x in label]) if len(label) else np.zeros(0, int)
    n_p, n_s, n_k = len(pid), len(settings), len(classes)
    group_of = None
    n_g = 0
    if groups:
        names = sorted({groups.get(x, x) for x in settings})
        n_g = len(names)
        group_of = np.array([names.index(groups.get(x, x)) for x in settings])
    # Start: majority vote per person.
    votes = np.zeros((n_p, n_k))
    np.add.at(votes, (p_inv, j_idx), 1.0)
    post = votes / votes.sum(axis=1, keepdims=True)
    prev = -np.inf
    ll = -np.inf
    it = 0
    while it < max_iter:
        it += 1
        # M step.
        prior = post.mean(axis=0)
        counts = np.zeros((n_s, n_k, n_k))
        np.add.at(counts, (s_idx, slice(None), j_idx), post[p_inv])
        if group_of is not None:
            # Pool each group's counts, then shrink every member toward its group.
            pooled = np.zeros((n_g, n_k, n_k))
            np.add.at(pooled, group_of, counts)
            pooled = (pooled + smoothing) / (pooled + smoothing).sum(axis=2, keepdims=True)
            conf = counts + strength * pooled[group_of] + smoothing
        else:
            conf = counts + smoothing
        conf /= conf.sum(axis=2, keepdims=True)
        # E step, in logs.
        logp = np.tile(np.log(prior + 1e-300), (n_p, 1))
        np.add.at(logp, p_inv, np.log(conf[s_idx, :, j_idx]))
        m = logp.max(axis=1, keepdims=True)
        w = np.exp(logp - m)
        z = w.sum(axis=1, keepdims=True)
        post = w / z
        ll = float((m.ravel() + np.log(z.ravel())).sum())
        if ll - prev < tol * abs(ll):
            break
        prev = ll
    obs_per_setting = np.bincount(s_idx, minlength=n_s)
    return AnnotatorModel(classes, settings, prior, conf, n_p, obs_per_setting, it, ll)


__all__ = ["AnnotatorModel", "fit"]
