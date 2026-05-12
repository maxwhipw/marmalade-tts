# Contributing to marmalade-tts

Thanks for considering a contribution! This is a small project — patches,
issues, and questions are all welcome.

## Quick start

```sh
git clone https://github.com/maxwhipw/marmalade-tts
cd marmalade-tts
pip install -e .
make test
```

The test suite (`make test`) runs everything except the smoke tests, which
require real engine binaries. Use `make test-all` to run smoke tests too.

## Adding a new TTS engine

See **[ENGINE-GUIDE.md](ENGINE-GUIDE.md)** for a step-by-step walkthrough of
every file you need to touch.

## Reporting bugs

Please open an issue using the bug-report template. Include:

- Engine and voice you were using
- Exact `marmalade-tts` command
- Output of `marmalade-tts --version`
- Output of `marmalade-tts config show` (redact paths if needed)
- Full error message

## Pull request guidelines

- Keep PRs focused — one logical change per PR.
- Run `make test` before pushing.
- Update `CHANGELOG.md` under the `## [Unreleased]` section if your change
  is user-visible.
- Avoid adding heavy runtime dependencies. The CLI wrapper depends on `pyyaml`
  and `num2words` only; engines live in their own venvs.
- Code style: standard Python, no formatter enforced. Match the surrounding
  code.

## Code of conduct

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree your contributions will be licensed under the
project's MIT license.
