# SCORCH public release -- paper reproduction targets.
#
# Windows users: `make` is usually unavailable; use the equivalent
#   python run_reproduction.py {smoke|fast|guide}
# (both entry points run the same stage table; `guide` only PRINTS the
# provider-level reconstruction guide -- there is no executable full route).
#
# Variables:
#   PYTHON    interpreter to use              (default: python)
#   DATA_DIR  processed-data deposit root     (default: scorch_data)
#   OUT_DIR   reproduced-output root          (default: reproduced)
#   PUB_DIR   assembled publication tree      (default: publication_outputs;
#             a SEPARATE destination from OUT_DIR, written by the final
#             publication-outputs assembly stage of the fast tier)
#   NBOOT     power-law bootstrap replicates  (default: 5000 = CANONICAL;
#             any smaller value is a quick, noncanonical run)

PYTHON   ?= python
DATA_DIR ?= scorch_data
OUT_DIR  ?= reproduced
PUB_DIR  ?= publication_outputs
NBOOT    ?= 5000

.PHONY: help data reconstruct smoke fast quick guide test clean

help:
	@echo "Targets:"
	@echo "  data        - download + verify the processed-data deposit into $(DATA_DIR)"
	@echo "  reconstruct - connected processed-field -> catalog reconstruction (installed package)"
	@echo "  smoke       - catalog validation + Table 1 + Figure 12 + Figure 2 (small subset)"
	@echo "  fast        - statistics, tables and all deposit-reproducible publication figures"
	@echo "                (canonical NBOOT=$(NBOOT) power-law bootstrap), then assembles"
	@echo "                the clean publication tree into $(PUB_DIR)"
	@echo "  quick       - fast with a REDUCED, NONCANONICAL bootstrap (NBOOT=200); smoke"
	@echo "                testing only -- its power-law numbers are NOT the published values"
	@echo "  guide       - print the provider-level ERA5 reconstruction guide (executes nothing)"
	@echo "  test        - run the scorch package unit/regression tests"

reconstruct:
	$(PYTHON) -m scorch.cli reproduce --base-dir $(DATA_DIR) --out-dir $(OUT_DIR) --route fast

# Requires the deposit identifier: set SCORCH_DATA_DOI (or edit in --doi /
# --url). The DOI is reserved while the Zenodo draft is private and becomes
# publicly resolvable at publication; fetch-data has no built-in default
# and fails with a clear message when nothing is configured.
data:
	$(PYTHON) -m scorch.cli fetch-data --dest $(DATA_DIR)
	$(PYTHON) -m scorch.cli validate-deposit --dir $(DATA_DIR)

smoke:
	$(PYTHON) run_reproduction.py smoke --data-dir $(DATA_DIR) --out-dir $(OUT_DIR)

fast:
	$(PYTHON) run_reproduction.py fast --data-dir $(DATA_DIR) --out-dir $(OUT_DIR) --pub-dir $(PUB_DIR) --nboot $(NBOOT)

# QUICK / NONCANONICAL: reduced bootstrap for smoke testing only.
quick:
	$(PYTHON) run_reproduction.py fast --data-dir $(DATA_DIR) --out-dir $(OUT_DIR) --pub-dir $(PUB_DIR) --nboot 200

guide:
	$(PYTHON) run_reproduction.py guide

test:
	$(PYTHON) -m pytest tests -q

clean:
	@echo "Removing materialized outputs under $(OUT_DIR) and $(PUB_DIR) (deposit and frozen assets untouched)"
	$(PYTHON) -c "import shutil; shutil.rmtree('$(OUT_DIR)', ignore_errors=True)"
	$(PYTHON) -c "import shutil; shutil.rmtree('$(PUB_DIR)', ignore_errors=True)"
