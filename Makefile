# Bequemlichkeit fuer alle, die lieber make tippen. run.sh macht die Arbeit.
.PHONY: serve sync bootstrap export stats test clean

serve:  ; ./run.sh serve
sync:   ; ./run.sh sync
export: ; ./run.sh export
stats:  ; ./run.sh stats

clean:
	rm -rf .venv web/data.json

bootstrap: ; ./run.sh bootstrap
test:      ; ./run.sh test
