# Third-party notices

CaseCite is licensed under the Elastic License 2.0 (see `LICENSE`). It is built
on the open-source packages below, each distributed under its own license,
reproduced here as those licenses require. This file is generated from the
installed dependency set (`backend/requirements.lock`, `frontend/package.json`
production dependencies); regenerate it when dependencies change:

```bash
pip install pip-licenses && cd backend && python -m piplicenses --format=json --with-urls
cd frontend && npx license-checker --production --json
```

No dependency is distributed under GPL, AGPL or SSPL. `psycopg2-binary` is LGPL
and is used unmodified as a dynamically linked library. PyMuPDF (AGPL) is
deliberately not a dependency (see `backend/requirements.txt`).

## Python (backend image)

| Package | Version | License |
|---|---|---|
| [aiofiles](https://github.com/Tinche/aiofiles) | 25.1.0 | Apache Software License |
| [aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) | 2.6.1 | Python Software Foundation License |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.14.1 | Apache-2.0 AND MIT |
| [aiosignal](https://github.com/aio-libs/aiosignal) | 1.4.0 | Apache Software License |
| [aiosqlite](https://aiosqlite.omnilib.dev) | 0.22.1 | MIT License |
| [alembic](https://alembic.sqlalchemy.org) | 1.14.0 | MIT License |
| [annotated-doc](https://github.com/fastapi/annotated-doc) | 0.0.4 | MIT |
| [annotated-types](https://github.com/annotated-types/annotated-types) | 0.7.0 | MIT License |
| [anthropic](https://github.com/anthropics/anthropic-sdk-python) | 0.18.1 | MIT |
| [anyio](https://anyio.readthedocs.io/en/stable/versionhistory.html) | 4.13.0 | MIT |
| asyncpg | 0.31.0 | Apache-2.0 |
| [attrs](https://www.attrs.org/en/stable/changelog.html) | 26.1.0 | MIT |
| [bcrypt](https://github.com/pyca/bcrypt/) | 5.0.0 | Apache Software License |
| [build](https://build.pypa.io) | 1.5.1 | MIT |
| [certifi](https://github.com/certifi/python-certifi) | 2026.2.25 | Mozilla Public License 2.0 (MPL 2.0) |
| [cffi](https://cffi.readthedocs.io/en/latest/whatsnew.html) | 2.0.0 | MIT |
| [charset-normalizer](https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md) | 3.4.6 | MIT |
| [chromadb](https://github.com/chroma-core/chroma) | 1.5.9 | Apache Software License |
| [click](https://github.com/pallets/click/) | 8.4.2 | BSD-3-Clause |
| [colorama](https://github.com/tartley/colorama) | 0.4.6 | BSD License |
| [cryptography](https://github.com/pyca/cryptography) | 46.0.6 | Apache-2.0 OR BSD-3-Clause |
| [distro](https://github.com/python-distro/distro) | 1.9.0 | Apache Software License |
| [dnspython](https://www.dnspython.org) | 2.8.0 | ISC License (ISCL) |
| [durationpy](https://github.com/icholy/durationpy) | 0.10 | MIT |
| [email-validator](https://github.com/JoshData/python-email-validator) | 2.3.0 | The Unlicense (Unlicense) |
| [et_xmlfile](https://foss.heptapod.net/openpyxl/et_xmlfile) | 2.0.0 | MIT License |
| [fastapi](https://github.com/fastapi/fastapi) | 0.139.0 | MIT |
| [filelock](https://github.com/tox-dev/py-filelock) | 3.29.4 | MIT |
| [flatbuffers](https://google.github.io/flatbuffers/) | 25.12.19 | Apache Software License |
| [frozenlist](https://github.com/aio-libs/frozenlist) | 1.8.0 | Apache-2.0 |
| [fsspec](https://github.com/fsspec/filesystem_spec) | 2026.6.0 | BSD-3-Clause |
| [googleapis-common-protos](https://github.com/googleapis/google-cloud-python/tree/main/packages/googleapis-common-protos) | 1.75.0 | Apache Software License |
| [greenlet](https://greenlet.readthedocs.io) | 3.3.2 | MIT AND PSF-2.0 |
| [grpcio](https://grpc.io) | 1.82.1 | Apache-2.0 |
| [h11](https://github.com/python-hyper/h11) | 0.16.0 | MIT License |
| [hf-xet](https://github.com/huggingface/xet-core) | 1.5.1 | Apache-2.0 |
| [httpcore](https://www.encode.io/httpcore/) | 1.0.9 | BSD-3-Clause |
| [httptools](https://github.com/MagicStack/httptools) | 0.7.1 | MIT |
| [httpx](https://github.com/encode/httpx) | 0.28.1 | BSD License |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | 1.25.1 | Apache Software License |
| [idna](https://github.com/kjd/idna) | 3.11 | BSD-3-Clause |
| [importlib_resources](https://github.com/python/importlib_resources) | 7.1.0 | Apache-2.0 |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT |
| [jsonschema-specifications](https://github.com/python-jsonschema/jsonschema-specifications) | 2025.9.1 | MIT |
| [kubernetes](https://github.com/kubernetes-client/python) | 36.0.2 | Apache Software License |
| [lxml](https://lxml.de/) | 6.0.2 | BSD-3-Clause |
| [Mako](https://www.makotemplates.org/) | 1.3.10 | MIT License |
| [markdown-it-py](https://github.com/executablebooks/markdown-it-py) | 4.2.0 | MIT License |
| [MarkupSafe](https://github.com/pallets/markupsafe/) | 3.0.3 | BSD-3-Clause |
| [mdurl](https://github.com/executablebooks/mdurl) | 0.1.2 | MIT License |
| [mmh3](https://pypi.org/project/mmh3/) | 5.2.1 | MIT License |
| [multidict](https://github.com/aio-libs/multidict) | 6.7.1 | Apache License 2.0 |
| [numpy](https://numpy.org) | 2.1.3 | BSD License |
| [oauthlib](https://github.com/oauthlib/oauthlib) | 3.3.1 | BSD-3-Clause |
| [olefile](https://www.decalage.info/python/olefileio) | 0.47 | BSD License |
| [onnxruntime](https://onnxruntime.ai) | 1.27.0 | MIT License |
| [openai](https://github.com/openai/openai-python) | 2.30.0 | Apache Software License |
| [openpyxl](https://openpyxl.readthedocs.io) | 3.1.5 | MIT License |
| [opentelemetry-api](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api) | 1.43.0 | Apache-2.0 |
| [opentelemetry-exporter-otlp-proto-common](https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-common) | 1.43.0 | Apache-2.0 |
| [opentelemetry-exporter-otlp-proto-grpc](https://github.com/open-telemetry/opentelemetry-python/tree/main/exporter/opentelemetry-exporter-otlp-proto-grpc) | 1.43.0 | Apache-2.0 |
| [opentelemetry-proto](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-proto) | 1.43.0 | Apache-2.0 |
| [opentelemetry-sdk](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-sdk) | 1.43.0 | Apache-2.0 |
| [opentelemetry-semantic-conventions](https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-semantic-conventions) | 0.64b0 | Apache-2.0 |
| [orjson](https://github.com/ijl/orjson) | 3.11.9 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| [overrides](https://github.com/mkorpela/overrides) | 7.7.0 | Apache License, Version 2.0 |
| [packaging](https://github.com/pypa/packaging) | 26.0 | Apache-2.0 OR BSD-2-Clause |
| [pillow](https://python-pillow.github.io) | 12.3.0 | MIT-CMU |
| [propcache](https://github.com/aio-libs/propcache) | 0.4.1 | Apache Software License |
| [protobuf](https://developers.google.com/protocol-buffers/) | 7.35.1 | 3-Clause BSD License |
| [psycopg2-binary](https://psycopg.org/) | 2.9.12 | GNU Library or Lesser General Public License (LGPL) |
| [pybase64](https://github.com/mayeut/pybase64) | 1.4.3 | BSD License |
| [pycparser](https://github.com/eliben/pycparser) | 3.0 | BSD-3-Clause |
| [pydantic](https://github.com/pydantic/pydantic) | 2.13.4 | MIT |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | 2.14.2 | MIT |
| [pydantic_core](https://github.com/pydantic) | 2.46.4 | MIT |
| [Pygments](https://pygments.org) | 2.20.0 | BSD-2-Clause |
| [PyJWT](https://github.com/jpadilla/pyjwt) | 2.13.0 | MIT |
| [pypdf](https://github.com/py-pdf/pypdf) | 6.14.2 | BSD-3-Clause |
| [PyPika](https://github.com/kayak/pypika) | 0.51.1 | Apache Software License |
| [pyproject_hooks](https://github.com/pypa/pyproject-hooks) | 1.2.0 | MIT License |
| [python-dateutil](https://github.com/dateutil/dateutil) | 2.9.0.post0 | Apache Software License; BSD License |
| [python-docx](https://github.com/python-openxml/python-docx) | 1.2.0 | MIT License |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | 1.2.2 | BSD-3-Clause |
| [python-http-client](https://github.com/sendgrid/python-http-client) | 3.3.7 | MIT |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.32 | Apache-2.0 |
| [python-pptx](https://github.com/scanny/python-pptx) | 1.0.2 | MIT License |
| [PyYAML](https://pyyaml.org/) | 6.0.3 | MIT License |
| [referencing](https://github.com/python-jsonschema/referencing) | 0.37.0 | MIT |
| [regex](https://github.com/mrabarnett/mrab-regex) | 2026.3.32 | Apache-2.0 AND CNRI-Python |
| [requests](https://requests.readthedocs.io) | 2.32.3 | Apache Software License |
| [requests-oauthlib](https://github.com/requests/requests-oauthlib) | 2.0.0 | BSD License |
| [rich](https://github.com/Textualize/rich) | 15.0.0 | MIT License |
| [rpds-py](https://github.com/crate-py/rpds) | 2026.6.3 | MIT |
| [sendgrid](https://github.com/sendgrid/sendgrid-python/) | 6.12.5 | MIT |
| [shellingham](https://github.com/sarugaku/shellingham) | 1.5.4 | ISC License (ISCL) |
| [six](https://github.com/benjaminp/six) | 1.17.0 | MIT License |
| [sniffio](https://github.com/python-trio/sniffio) | 1.3.1 | Apache Software License; MIT License |
| [SQLAlchemy](https://www.sqlalchemy.org) | 2.0.48 | MIT |
| [starlette](https://github.com/Kludex/starlette) | 1.3.1 | BSD-3-Clause |
| [striprtf](https://github.com/joshy/striprtf) | 0.0.33 | BSD-3-Clause |
| [tenacity](https://github.com/jd/tenacity) | 9.1.4 | Apache Software License |
| [tiktoken](https://github.com/openai/tiktoken) | 0.12.0 | MIT License

Copyright (c) 2022 OpenAI, Shantanu Jain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
 |
| [tokenizers](https://github.com/huggingface/tokenizers) | 0.23.1 | Apache Software License |
| [tqdm](https://tqdm.github.io) | 4.67.3 | MPL-2.0 AND MIT |
| [typer](https://github.com/fastapi/typer) | 0.25.1 | MIT |
| [typing-inspection](https://github.com/pydantic/typing-inspection) | 0.4.2 | MIT |
| [typing_extensions](https://github.com/python/typing_extensions) | 4.15.0 | PSF-2.0 |
| [urllib3](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst) | 2.6.3 | MIT |
| [uvicorn](https://www.uvicorn.org/) | 0.32.1 | BSD License |
| [watchfiles](https://github.com/samuelcolvin/watchfiles) | 1.1.1 | MIT License |
| [websocket-client](https://github.com/websocket-client/websocket-client.git) | 1.9.0 | Apache Software License |
| [websockets](https://github.com/python-websockets/websockets) | 16.0 | BSD-3-Clause |
| [xlrd](http://www.python-excel.org/) | 2.0.2 | BSD License |
| [xlsxwriter](https://github.com/jmcnamara/XlsxWriter) | 3.2.9 | BSD License |
| [yarl](https://github.com/aio-libs/yarl) | 1.23.0 | Apache-2.0 |

## JavaScript (frontend bundle, production dependencies)

| Package | Version | License |
|---|---|---|
| [@azure/msal-browser](https://github.com/AzureAD/microsoft-authentication-library-for-js) | 3.30.0 | MIT |
| [@azure/msal-common](https://github.com/AzureAD/microsoft-authentication-library-for-js) | 14.16.1 | MIT |
| [@types/react](https://github.com/DefinitelyTyped/DefinitelyTyped) | 19.2.14 | MIT |
| [ansi-regex](https://github.com/chalk/ansi-regex) | 5.0.1 | MIT |
| [ansi-styles](https://github.com/chalk/ansi-styles) | 4.3.0 | MIT |
| [camelcase](https://github.com/sindresorhus/camelcase) | 5.3.1 | MIT |
| [cliui](https://github.com/yargs/cliui) | 6.0.0 | ISC |
| [color-convert](https://github.com/Qix-/color-convert) | 2.0.1 | MIT |
| [color-name](https://github.com/colorjs/color-name) | 1.1.4 | MIT |
| [cookie](https://github.com/jshttp/cookie) | 1.1.1 | MIT |
| [csstype](https://github.com/frenic/csstype) | 3.2.3 | MIT |
| [decamelize](https://github.com/sindresorhus/decamelize) | 1.2.0 | MIT |
| [dijkstrajs](https://github.com/tcort/dijkstrajs) | 1.0.3 | MIT |
| [emoji-regex](https://github.com/mathiasbynens/emoji-regex) | 8.0.0 | MIT |
| [find-up](https://github.com/sindresorhus/find-up) | 4.1.0 | MIT |
| [get-caller-file](https://github.com/stefanpenner/get-caller-file) | 2.0.5 | ISC |
| [is-fullwidth-code-point](https://github.com/sindresorhus/is-fullwidth-code-point) | 3.0.0 | MIT |
| [js-tokens](https://github.com/lydell/js-tokens) | 4.0.0 | MIT |
| [locate-path](https://github.com/sindresorhus/locate-path) | 5.0.0 | MIT |
| [loose-envify](https://github.com/zertosh/loose-envify) | 1.4.0 | MIT |
| [lucide-react](https://github.com/lucide-icons/lucide) | 0.344.0 | ISC |
| [p-limit](https://github.com/sindresorhus/p-limit) | 2.3.0 | MIT |
| [p-locate](https://github.com/sindresorhus/p-locate) | 4.1.0 | MIT |
| [p-try](https://github.com/sindresorhus/p-try) | 2.2.0 | MIT |
| [path-exists](https://github.com/sindresorhus/path-exists) | 4.0.0 | MIT |
| [pngjs](https://github.com/lukeapage/pngjs) | 5.0.0 | MIT |
| [qrcode](https://github.com/soldair/node-qrcode) | 1.5.4 | MIT |
| [react](https://github.com/facebook/react) | 18.3.1 | MIT |
| [react-dom](https://github.com/facebook/react) | 18.3.1 | MIT |
| [react-router](https://github.com/remix-run/react-router) | 7.18.2 | MIT |
| [react-router-dom](https://github.com/remix-run/react-router) | 7.18.2 | MIT |
| [require-directory](https://github.com/troygoode/node-require-directory) | 2.1.1 | MIT |
| [require-main-filename](https://github.com/yargs/require-main-filename) | 2.0.0 | ISC |
| [scheduler](https://github.com/facebook/react) | 0.23.2 | MIT |
| [set-blocking](https://github.com/yargs/set-blocking) | 2.0.0 | ISC |
| [set-cookie-parser](https://github.com/nfriedly/set-cookie-parser) | 2.7.2 | MIT |
| [string-width](https://github.com/sindresorhus/string-width) | 4.2.3 | MIT |
| [strip-ansi](https://github.com/chalk/strip-ansi) | 6.0.1 | MIT |
| [which-module](https://github.com/nexdrew/which-module) | 2.0.1 | ISC |
| [wrap-ansi](https://github.com/chalk/wrap-ansi) | 6.2.0 | MIT |
| [y18n](https://github.com/yargs/y18n) | 4.0.3 | ISC |
| [yargs](https://github.com/yargs/yargs) | 15.4.1 | MIT |
| [yargs-parser](https://github.com/yargs/yargs-parser) | 18.1.3 | ISC |
| [zustand](https://github.com/pmndrs/zustand) | 5.0.11 | MIT |

## Fonts

Inter, JetBrains Mono and Source Serif 4 are loaded from Google Fonts under the SIL Open Font License 1.1.
