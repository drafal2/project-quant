# validation/

Cross-validation suites that compare the in-house `montecarlo/` implementations against an external reference. These run **outside** the default `pytest tests/` path because they introduce heavy optional dependencies and are not part of the per-commit correctness guarantee.

## quantlib_xref/

Cross-checks every layer of `montecarlo/` (PRNG sequences, low-discrepancy points, inverse-cumulative-normal transforms, end-to-end Black-Scholes pricing) against [QuantLib-Python](https://www.quantlib.org/). The companion document is [`REPORT.md`](REPORT.md), which records the observed numerical differences and explains each one.

### Install

```bash
pip install -e ".[validation]"
```

### Run

```bash
.venv/Scripts/python -m pytest validation/quantlib_xref -q
```

If QuantLib is not installed, the suite is skipped cleanly (`pytest.importorskip` in `conftest.py`). The core `tests/` suite is unaffected by the presence or absence of QuantLib.

### What is checked

| File | Layer | Reference |
|---|---|---|
| `test_joe_kuo_data.py` | Sobol direction-number table | `ql.SobolRsg(JoeKuoD6)` |
| `test_inverse_cdf_pointwise.py` | `MoroTransform`, `AcklamTransform`, `WichuraAS241Transform` | `ql.MoroInverseCumulativeNormal`, `ql.InverseCumulativeNormal`, `scipy.special.ndtri` |
| `test_uniform_distributional.py` | All five `Sampler` subclasses | `ql.MersenneTwisterUniformRng`, `ql.SobolRsg`, `ql.HaltonRsg` |
| `test_bs_pricing_pairs.py` | All 21 compatible `(sampler, transform)` pairs | `ql.BlackCalculator` closed-form price |

See [`REPORT.md`](REPORT.md) for the observed numerical agreement at each layer and why the residuals look the way they do.
