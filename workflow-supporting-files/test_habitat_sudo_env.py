"""Run with python3 workflow-supporting-files/test_habitat_sudo_env.py."""

import os
from pathlib import Path
import re
import subprocess
import tempfile


workflow = (Path(__file__).resolve().parents[1] /
            ".github/workflows/grype-hab-package-scan.yml").read_text()
blocks = re.findall(r"        run: \|\n((?: {12}.*\n|\n)+)", workflow)
scripts = [block for block in blocks if "sudo" in block and "HAB_AUTH_TOKEN" in block]
assert len(scripts) == 5, "Exercise every privileged Habitat installation"

for script in scripts:
    if "hartifacts=" in script:
        script = script[script.index("hartifacts="):]
    for input_token, secret_token in [("input-token", "secret-token"),
                                      ("", "secret-token"), ("", "")]:
        values = {
            "inputs.hab_auth_token": input_token,
            "secrets.HAB_AUTH_TOKEN": secret_token,
            "inputs.hab_origin": "chef",
            "inputs.hab_package": "fauxhai",
            "inputs.hab_version": "9.4.29",
            "inputs.hab_release": "",
            "inputs.hab_channel": "unstable",
        }
        rendered = re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}",
                          lambda match: values[match[1]], script)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "results").mkdir()
            (root / "results/package.hart").touch()
            commands = root / "commands"
            bin_dir = root / "bin"
            bin_dir.mkdir()
            stubs = {
                "sudo": '#!/bin/bash\n'
                        'if [[ "$1" == -E ]]; then shift; fi\n'
                        'exec env -i PATH="$PATH" "$@"\n',
                "curl": '#!/bin/bash\n'
                        "echo 'hab pkg install chef/hab'\n",
                "hab": '#!/bin/bash\n'
                       f'[[ "${{HAB_AUTH_TOKEN:-}}" == "{input_token or secret_token}" ]] || exit 10\n'
                       '[[ "$HAB_LICENSE" == accept-no-persist ]] || exit 11\n'
                       f'printf "%s\\n" "$*" >> "{commands}"\n',
            }
            for name, content in stubs.items():
                executable = bin_dir / name
                executable.write_text(content)
                executable.chmod(0o755)
            environment = {
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "HAB_LICENSE": "accept-no-persist",
            }
            if "hartifacts=" in script:
                environment["HAB_AUTH_TOKEN"] = input_token or secret_token
            result = subprocess.run(["bash", "-e", "-c", rendered], cwd=root,
                                    env=environment, capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            installed = commands.read_text()
            if "INSTALL_CMD=" in script:
                assert installed == "pkg install chef/fauxhai/9.4.29 --channel unstable\n"
            elif "hartifacts=" in script:
                assert installed == "pkg install results/package.hart\n"
            else:
                assert "pkg install chef/hab\n" in installed
            assert "input-token" not in result.stdout
            assert "secret-token" not in result.stdout
            (bin_dir / "hab").write_text("#!/bin/bash\nexit 17\n")
            failed = subprocess.run(["bash", "-e", "-c", rendered], cwd=root,
                                    env=environment, capture_output=True, text=True)
            assert failed.returncode == 17, "Habitat failures must propagate"

print("Habitat sudo environment checks passed (5 paths, 3 token cases).")
