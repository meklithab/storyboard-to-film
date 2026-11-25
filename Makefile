PYTHON ?= python

.PHONY: film validate narration keyframes shots subtitles assemble smoketest radio_cut

film: validate narration keyframes shots subtitles assemble

validate:
	"$(PYTHON)" pipeline/validate.py

narration:
	"$(PYTHON)" pipeline/narration.py

keyframes:
	"$(PYTHON)" pipeline/keyframes.py

shots:
	"$(PYTHON)" pipeline/shots.py

subtitles:
	"$(PYTHON)" pipeline/subtitles.py

assemble:
	"$(PYTHON)" pipeline/assemble.py

smoketest:
	"$(PYTHON)" pipeline/smoketest.py

radio_cut:
	"$(PYTHON)" pipeline/radio_cut.py
