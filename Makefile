SHELL=/bin/bash

pkg_name=gcardvault
pkg_version:=$(shell cat src/${pkg_name}/VERSION.txt | xargs)
cli_name:=${pkg_name}

container_hub_acct=rtomac
image_name:=${pkg_name}
image_tag=latest
image_version_tag:=${pkg_version}
image_platforms=linux/amd64,linux/arm64,linux/arm/v7,linux/arm/v6

all: dist

.PHONY: devenv
devenv:
	[ ! -d "./.devenv" ] && virtualenv .devenv || true
	. ./.devenv/bin/activate && pip install -e '.[dev,test,release]'
	@echo ""
	@echo "Run 'source ./.devenv/bin/activate' to activate the virtual env"

.PHONY: dist
dist:
	python3 setup.py sdist
	ln -f "dist/${pkg_name}-${pkg_version}.tar.gz" "dist/${pkg_name}-latest.tar.gz"

.PHONY: test
test:
	pytest

.PHONY: docker-build
docker-build: dist
	docker build \
		-t ${image_name}:local \
		.

user=foo.bar@gmail.com
.PHONY: docker-run
docker-run:
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.${pkg_name} \
		-v ${PWD}/output:/root/${pkg_name} \
		-v ${PWD}/bin/${cli_name}:/usr/local/bin/${cli_name} \
		-v ${PWD}/src/${pkg_name}:/usr/local/lib/python3.9/site-packages/${pkg_name} \
		${image_name}:local sync ${user}

.PHONY: docker-test
docker-test:
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.${pkg_name} \
		-v ${PWD}/output:/root/${pkg_name} \
		-v ${PWD}:/usr/local/src/${pkg_name} \
		--workdir /usr/local/src/${pkg_name} \
		--entrypoint pytest \
		${image_name}:local

.PHONY: docker-debug
docker-debug:
	docker run -it --rm \
		-v ${PWD}/.conf:/root/.${pkg_name} \
		-v ${PWD}/output:/root/${pkg_name} \
		-v ${PWD}/bin/${cli_name}:/usr/local/bin/${cli_name} \
		-v ${PWD}/src/${pkg_name}:/usr/local/lib/python3.9/site-packages/${pkg_name} \
		--entrypoint /bin/bash \
		${image_name}:local

.PHONY: release
release: test
	twine upload --repository testpypi dist/${pkg_name}-${pkg_version}.tar.gz
	
	twine upload dist/${pkg_name}-${pkg_version}.tar.gz

	docker buildx build \
		--tag "${container_hub_acct}/${image_name}:${image_tag}" \
		--tag "${container_hub_acct}/${image_name}:${image_version_tag}" \
		--platform "${image_platforms}" \
		--push \
		.
