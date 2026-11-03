#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Resolve a locked CPAN module through the actual PerlNavigator server."""

import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlparse

root, helper = map(lambda value: Path(value).resolve(), sys.argv[1:])
settings = {
    "perlcriticEnabled": False,
    "perltidyEnabled": False,
    "logging": False,
    "enableProgress": False,
}
with (root / "editor.log").open("w") as log:
    process = subprocess.Popen(
        [helper, "--project", root, "shell", "--", "perlnavigator", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=log,
    )
    messages = queue.Queue()

    def reader():
        try:
            while True:
                headers = {}
                while True:
                    line = process.stdout.readline()
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    name, value = line.decode().split(":", 1)
                    headers[name.lower()] = value.strip()
                body = process.stdout.read(int(headers["content-length"]))
                messages.put(json.loads(body))
        except Exception as error:
            messages.put(error)

    threading.Thread(target=reader, daemon=True).start()
    next_id = 0

    def send(message):
        body = json.dumps({"jsonrpc": "2.0", **message}).encode()
        process.stdin.write(
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
        )
        process.stdin.flush()

    def request(method, params):
        global next_id
        next_id += 1
        identifier = next_id
        send({"id": identifier, "method": method, "params": params})
        deadline = time.monotonic() + 120
        while True:
            response = messages.get(timeout=max(0.1, deadline - time.monotonic()))
            if isinstance(response, Exception):
                raise response
            if response.get("id") == identifier and "method" not in response:
                assert "error" not in response, response
                return response.get("result")
            if "id" in response and "method" in response:
                method = response["method"]
                result = (
                    [{"uri": root.as_uri(), "name": "example"}]
                    if method == "workspace/workspaceFolders"
                    else [settings for _ in response["params"]["items"]]
                    if method == "workspace/configuration"
                    else None
                )
                send({"id": response["id"], "result": result})
            if time.monotonic() > deadline:
                raise TimeoutError(method)

    try:
        initialized = request(
            "initialize",
            {
                "processId": None,
                "rootUri": root.as_uri(),
                "workspaceFolders": [{"uri": root.as_uri(), "name": "example"}],
                "capabilities": {},
            },
        )
        assert initialized["capabilities"].get("definitionProvider")
        send({"method": "initialized", "params": {}})
        send(
            {
                "method": "workspace/didChangeConfiguration",
                "params": {"settings": {"perlnavigator": settings}},
            }
        )
        source = root / "lib/Purifier/Example.pm"
        text = source.read_text()
        uri = source.as_uri()
        send(
            {
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "perl",
                        "version": 1,
                        "text": text,
                    }
                },
            }
        )
        lines = text.splitlines()
        line = next(
            index
            for index, value in enumerate(lines)
            if value.startswith("use JSON::MaybeXS")
        )
        position = {"line": line, "character": lines[line].index("JSON") + 3}
        deadline = time.monotonic() + 90
        while True:
            result = request(
                "textDocument/definition",
                {"textDocument": {"uri": uri}, "position": position},
            )
            if result:
                break
            assert process.poll() is None, (root / "editor.log").read_text()
            if time.monotonic() > deadline:
                raise AssertionError(
                    "PerlNavigator did not resolve the dependency: "
                    + (root / "editor.log").read_text()[-4000:]
                )
            time.sleep(0.3)
        location = result[0] if isinstance(result, list) else result
        target = Path(
            unquote(urlparse(location.get("uri", location.get("targetUri"))).path)
        ).resolve()
        assert str(target).startswith("/nix/store/") and target.name == "MaybeXS.pm", (
            result
        )
        assert target.is_file()
        request("shutdown", None)
        send({"method": "exit", "params": None})
        process.stdin.close()
        assert process.wait(timeout=10) == 0
        print("PerlNavigator definition:", target)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
