# Contributing

Thanks for your interest in contributing to qwenpaw-openviking.

## Issues and pull requests

- Open an issue first for bugs or feature proposals, so the approach can be discussed before you invest in a large change.
- Keep pull requests small and focused; one concern per PR.
- Make sure `python3 -m unittest discover -s tests -v` passes before submitting. CI runs the same command plus a compile check on Python 3.12.

## Code style

- **Standard library only.** This project has zero third-party runtime and test dependencies; do not add any.
- Target Python 3.12+.
- No comments unless the code is non-obvious — prefer clear names and simple structure over explanatory comments.

## License

This project is licensed under AGPL-3.0, matching the upstream [volcengine/OpenViking](https://github.com/volcengine/OpenViking) project it is adapted from. By submitting a contribution, you agree that it is licensed under AGPL-3.0.
