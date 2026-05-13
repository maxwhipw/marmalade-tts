VERSION := $(shell python3 -c "from marmalade_tts import __version__; print(__version__)")
SYSTEMD_SYSTEM_DIR := build/systemd-system

# Development
.PHONY: test test-all lint clean

test:
	python3 -m pytest tests/ -v -m "not smoke"

test-all:
	python3 -m pytest tests/ -v

lint:
	python3 -m py_compile marmalade_tts/*.py marmalade_tts/engines/*.py

# Generate system-scoped systemd unit files for .deb/.rpm/AUR packages.
# The repo's systemd/*.service files target user installs (%h/.local/share/...);
# system packages need /usr/share/... — sed rewrites the daemon script path.
.PHONY: systemd-system
systemd-system:
	@rm -rf $(SYSTEMD_SYSTEM_DIR)
	@mkdir -p $(SYSTEMD_SYSTEM_DIR)
	@for f in systemd/marmalade-*.service; do \
	  sed 's|%h/\.local/share/marmalade-tts/daemon|/usr/share/marmalade-tts/daemon|' \
	    $$f > $(SYSTEMD_SYSTEM_DIR)/$$(basename $$f); \
	done

# Packaging
.PHONY: pypi deb rpm install

pypi:
	python3 -m build
	@echo "Upload: python3 -m twine upload dist/*"

deb: systemd-system
	@command -v fpm >/dev/null || { echo "Install fpm: gem install fpm"; exit 1; }
	fpm -s dir -t deb \
		-n marmalade-tts \
		-v $(VERSION) \
		--description "Unified local TTS CLI — kitten | kokoro | piper | coqui | pocket" \
		--license MIT \
		--url "https://github.com/maxwhipw/marmalade-tts" \
		--maintainer "marmalade-tts contributors" \
		--category sound \
		--depends python3 \
		--depends python3-yaml \
		--depends python3-num2words \
		--deb-recommends sox \
		--after-install packaging/postinst.sh \
		--before-remove packaging/prerm.sh \
		--deb-no-default-config-files \
		marmalade_tts/=/usr/lib/marmalade-tts/marmalade_tts/ \
		marmalade-tts=/usr/bin/marmalade-tts \
		config-default.yaml=/usr/share/marmalade-tts/config-default.yaml \
		daemon/=/usr/share/marmalade-tts/daemon/ \
		LICENSE=/usr/share/doc/marmalade-tts/LICENSE \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-kitten.service=/usr/lib/systemd/user/marmalade-kitten.service \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-kokoro.service=/usr/lib/systemd/user/marmalade-kokoro.service \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-piper.service=/usr/lib/systemd/user/marmalade-piper.service \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-coqui.service=/usr/lib/systemd/user/marmalade-coqui.service \
		scripts/speak-selection=/usr/share/marmalade-tts/scripts/speak-selection \
		scripts/speak-clipboard=/usr/share/marmalade-tts/scripts/speak-clipboard \
		scripts/marmalade-pipe=/usr/share/marmalade-tts/scripts/marmalade-pipe
	@echo "Built: marmalade-tts_$(VERSION)_amd64.deb"

rpm: systemd-system
	@command -v fpm >/dev/null || { echo "Install fpm: gem install fpm"; exit 1; }
	fpm -s dir -t rpm \
		-n marmalade-tts \
		-v $(VERSION) \
		--description "Unified local TTS CLI — kitten | kokoro | piper | coqui | pocket" \
		--license MIT \
		--url "https://github.com/maxwhipw/marmalade-tts" \
		--depends python3 \
		--depends python3-pyyaml \
		--depends python3-num2words \
		marmalade_tts/=/usr/lib/marmalade-tts/marmalade_tts/ \
		marmalade-tts=/usr/bin/marmalade-tts \
		config-default.yaml=/usr/share/marmalade-tts/config-default.yaml \
		daemon/=/usr/share/marmalade-tts/daemon/ \
		LICENSE=/usr/share/doc/marmalade-tts/LICENSE \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-kitten.service=/usr/lib/systemd/user/marmalade-kitten.service \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-kokoro.service=/usr/lib/systemd/user/marmalade-kokoro.service \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-piper.service=/usr/lib/systemd/user/marmalade-piper.service \
		$(SYSTEMD_SYSTEM_DIR)/marmalade-coqui.service=/usr/lib/systemd/user/marmalade-coqui.service

install:
	bash install.sh

clean:
	rm -rf dist/ build/ *.egg-info *.deb *.rpm $(SYSTEMD_SYSTEM_DIR)
	find . -name __pycache__ -type d -exec rm -rf {} +
	find . -name '*.pyc' -delete
