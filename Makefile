_WAF_SRC_DIR = subtree-waf
_VIRTUALENV_SRC_DIR = subtree-virtualenv
_TOOLS = $(wildcard tools/*.py)
_TOOLS_LIST = $(subst $(space),$(comma),$(foreach tool,$(_TOOLS),$(shell pwd)/$(tool)))
_DATA = $(wildcard tools/pylintrc)
_DATA_LIST = $(subst $(space),$(comma),$(foreach data,$(_DATA),$(shell pwd)/$(data)))
_VE = $(wildcard $(_VIRTUALENV_SRC_DIR)/virtualenv.py $(_VIRTUALENV_SRC_DIR)/virtualenv_support/*.whl)
_VE_LIST = $(subst $(space),$(comma),$(foreach data,$(_VE),$(shell pwd)/$(data)))

# black magic for replace space with comma
comma:= ,
empty:=
space:= $(empty) $(empty)

# don't go looking for other wscript files
NOCLIMB := 1

.PHONY = pyenv


################################################################################
# Target to bootstrap the waf build script
# NOCLIMB is set and 'configure build'
# is used to allow this process to work in a subtree that has a higher wscript file
waf: $(_TOOLS) $(_DATA) $(_VE)
	$(MAKE) pylint
	cd $(_WAF_SRC_DIR) && ./waf-light -v --make-waf \
		--tools=$(_TOOLS_LIST),$(_DATA_LIST),$(_VE_LIST) \
		configure build
	cp $(_WAF_SRC_DIR)/waf .

pylint:
	waf-pyenv/bin/pylint -E -r n --rcfile=tools/pylintrc-wscript tools

pyenv:
	python $(_VIRTUALENV_SRC_DIR)/virtualenv.py waf-pyenv
	waf-pyenv/bin/pip install pylint pylint-django pyflakes django

clean:
	rm -f waf
