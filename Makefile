PYTHON ?= python

.PHONY: film test validate narration retime keyframes shots music subtitles assemble smoketest radio_cut

film: validate narration retime keyframes shots music subtitles assemble

test: validate music
	"$(PYTHON)" tests/test_timeline.py

validate:
	"$(PYTHON)" pipeline/validate.py

narration:
	"$(PYTHON)" pipeline/narration.py

retime:
	"$(PYTHON)" pipeline/retime.py

keyframes:
	"$(PYTHON)" pipeline/keyframes.py

shots:
	"$(PYTHON)" pipeline/shots.py

music:
	"$(PYTHON)" pipeline/music.py

subtitles:
	"$(PYTHON)" pipeline/subtitles.py

assemble:
	"$(PYTHON)" pipeline/assemble.py

smoketest:
	"$(PYTHON)" pipeline/smoketest.py

radio_cut:
	"$(PYTHON)" pipeline/radio_cut.py
