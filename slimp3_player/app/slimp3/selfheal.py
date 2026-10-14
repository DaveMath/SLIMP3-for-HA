"""After an update, add any new options (with their defaults) to the saved configuration.

Home Assistant keeps the saved options and the Configuration form separately, so an app updated from an older version
can have a saved configuration that lacks the new options. This reads the defaults shipped with the app
(/app/config.yaml, a copy of config.yaml) and writes the missing ones back through the Supervisor's own-app endpoint
(/addons/self/options). Existing values are never changed. Any failure is logged and ignored; the app already falls
back to the same defaults when an option is missing.
"""
import json
import os
import urllib.request

DEFAULTS_PATH = os.environ.get("SLIMP3_DEFAULTS", "/app/config.yaml")
SUPERVISOR = os.environ.get("SLIMP3_SUPERVISOR", "http://supervisor")


def missing_options(opts, defaults_path=DEFAULTS_PATH):
    """The default options (name -> value) that `opts` does not have yet."""
    import yaml
    with open(defaults_path) as f:
        defaults = (yaml.safe_load(f) or {}).get("options") or {}
    return {k: v for k, v in defaults.items() if k not in opts}


def heal(opts, log=print):
    """Fill `opts` in place with missing defaults and save them to Home Assistant. Returns the names added."""
    try:
        add = missing_options(opts)
    except Exception as e:
        log("options: could not read the defaults (%s)" % e)
        return []
    if not add:
        return []
    opts.update(add)
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        log("options: new options %s use their defaults (no Supervisor token to save them)" % ", ".join(sorted(add)))
        return list(add)
    try:
        req = urllib.request.Request(
            SUPERVISOR + "/addons/self/options", data=json.dumps({"options": opts}).encode(), method="POST",
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        log("options: added new options to the saved configuration: %s" % ", ".join(sorted(add)))
    except Exception as e:
        log("options: new options %s use their defaults (could not save them: %s)" % (", ".join(sorted(add)), e))
    return list(add)
