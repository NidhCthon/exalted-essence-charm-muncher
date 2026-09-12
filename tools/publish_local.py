"""Publish the built module to a Foundry server you control.

There is no public release of this module and there should not be: the packs
are the publisher's text (see NOTICE). Instead the built module is served to
one Foundry server over loopback, so that server can install and update it
the way it would any other module, without any of it leaving the machine.

    python tools/publish_local.py            # upload, so Foundry sees an update
    python tools/publish_local.py --deploy   # also swap the live packs now

Uploading is enough for Foundry to offer an update on its Setup screen.
--deploy additionally installs it straight into the data directory, which is
faster but stops the server for a moment, since compendium packs are open
LevelDB files that cannot be swapped underneath a running world.

The server is described by environment variables rather than written down
here, because this repository is public and the server is not:

    FOUNDRY_SSH_HOST     user@host of the Foundry box        (required)
    FOUNDRY_SSH_KEY      path to the ssh key                 (optional)
    FOUNDRY_MODULE_DIR   where the module server serves from
                         (default /var/www/foundry-modules)
    FOUNDRY_DATA_DIR     Foundry's data directory
                         (default /var/lib/foundryvtt)
    FOUNDRY_SERVICE      systemd unit to stop for --deploy
                         (default foundryvtt)
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "module"


def setting(name, default=None):
    value = os.environ.get(name, default)
    if not value:
        sys.exit("{} is not set. See the module docstring for what this "
                 "script needs.".format(name))
    return value


def run(command):
    result = subprocess.run(command)
    if result.returncode != 0:
        sys.exit("failed: {}".format(" ".join(str(c) for c in command)))


def build_zip(manifest, into):
    """Zip the module as Foundry expects, minus the LevelDB lock files."""
    archive = into / "module-{}.zip".format(manifest["version"])
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(MODULE.rglob("*")):
            if path.is_file() and path.name != "LOCK":
                bundle.write(path, path.relative_to(MODULE).as_posix())
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true",
                        help="also install it into the live data directory")
    args = parser.parse_args()

    if not (MODULE / "module.json").exists():
        sys.exit("module/ is not built. Run tools/build_all.py first.")
    manifest = json.loads((MODULE / "module.json").read_text(encoding="utf-8"))
    identifier, version = manifest["id"], manifest["version"]

    host = setting("FOUNDRY_SSH_HOST")
    key = os.environ.get("FOUNDRY_SSH_KEY")
    module_dir = setting("FOUNDRY_MODULE_DIR", "/var/www/foundry-modules")
    data_dir = setting("FOUNDRY_DATA_DIR", "/var/lib/foundryvtt")
    service = setting("FOUNDRY_SERVICE", "foundryvtt")

    ssh = ["ssh"] + (["-i", key] if key else []) + [host]
    scp = ["scp"] + (["-i", key] if key else [])

    with tempfile.TemporaryDirectory() as workspace:
        staging = Path(workspace)
        archive = build_zip(manifest, staging)
        print("built {} ({:.1f} MB)".format(
            archive.name, archive.stat().st_size / 1048576))

        run(scp + [str(archive), str(MODULE / "module.json"),
                   "{}:~/".format(host)])

        served = "{}/{}".format(module_dir, identifier)
        remote = [
            "sudo mkdir -p {}".format(served),
            "sudo mv ~/{} ~/module.json {}/".format(archive.name, served),
            "sudo chmod -R a+rX {}".format(module_dir),
            "echo published: $(ls {} | tr '\\n' ' ')".format(served),
        ]
        if args.deploy:
            installed = "{}/Data/modules/{}".format(data_dir, identifier)
            # The rollback copy goes outside Data/modules. Foundry scans that
            # directory and reports every folder in it as a module, so a
            # backup left beside the real one is logged as an invalid module
            # on every startup.
            rollback = "/tmp/{}.previous".format(identifier)
            remote += [
                "sudo systemctl stop {}".format(service),
                "sudo rm -rf {}".format(rollback),
                "sudo mv {} {} || true".format(installed, rollback),
                "sudo mkdir -p {}".format(installed),
                "sudo unzip -q {}/{} -d {}".format(
                    served, archive.name, installed),
                "sudo chown -R --reference={} {}".format(data_dir, installed),
                "sudo systemctl start {}".format(service),
                "echo installed: $(sudo cat {}/module.json | "
                "python3 -c 'import json,sys;print(json.load(sys.stdin)[\"version\"])')"
                .format(installed),
                # Reporting success before the server answers would make a
                # failed start look like a good deploy.
                "for i in $(seq 1 15); do code=$(curl -s -o /dev/null -w "
                "'%{http_code}' http://127.0.0.1:30000/ || true); "
                "[ \"$code\" != \"000\" ] && break; sleep 2; done; "
                "echo \"serving: http $code\"",
                "echo rollback kept at {}".format(rollback),
            ]
        run(ssh + [" && ".join(remote)])

    print()
    print("{} {} published to {}".format(identifier, version, host))
    if args.deploy:
        print("installed into the data directory; the world will need a")
        print("restart to pick up new packs.")
    else:
        print("Foundry will offer it as an update on the Setup screen.")


if __name__ == "__main__":
    main()
