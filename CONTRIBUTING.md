# Contributing

Thanks for your interest in SCORCH.

* **Bug reports / questions**: open a GitHub issue with a minimal
  reproducible example and your Python / package versions.
* **Pull requests**: fork, create a feature branch, add or update tests under
  `tests/`, and make sure `pytest` passes before submitting.
* **Scientific kernel**: the modules under `src/scorch/_kernel/` are verbatim
  copies of the canonical research code that produced the published catalog.
  Changes there alter scientific results and will only be accepted with a
  documented scientific justification and updated regression baselines.
* **Style**: PEP 8, ASCII-safe source, no hard-coded absolute paths.

By contributing you agree that your contributions are licensed under the MIT
License of this repository.
