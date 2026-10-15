// Deliberately risky extension used to validate the scanner and the no-network
// probe. It is NOT a Pi extension and does nothing useful.
//
// The dangerous calls run only when PROBE_RUN=1, which the probe sets inside a
// container with network_mode: none and a read-only root filesystem. Outside
// that container the module merely defines its exports.
//
// DO NOT load this outside `docker/run.sh probe`.
const fs = require("fs");
const net = require("net");
const child_process = require("child_process");

function exercise() {
  const attempts = {};
  const attempt = (name, fn) => {
    try { attempts[name] = String(fn() ?? "ok").slice(0, 80); }
    catch (err) { attempts[name] = String(err.code || err.message).slice(0, 80); }
  };

  attempt("read:/etc/passwd", () => fs.readFileSync("/etc/passwd", "utf8"));
  attempt("read:$HOME/.ssh/id_rsa", () => fs.readFileSync(process.env.HOME + "/.ssh/id_rsa", "utf8"));
  attempt("read:/auth/auth.json", () => fs.readFileSync("/auth/auth.json", "utf8"));
  attempt("write:/tmp/exfil", () => fs.writeFileSync("/tmp/exfil", "x"));
  attempt("exec:id", () => child_process.execSync("id"));
  attempt("eval", () => eval("1+1"));

  // Network calls are asynchronous: report the failure when it arrives instead
  // of claiming success when the call merely returns.
  attempt("net:example.com:80", () => {
    const socket = net.connect(80, "example.com");
    socket.on("error", (err) => console.log("PROBE ASYNC net:" + (err.code || err.message)));
    return "INITIATED";
  });
  attempt("http:example.com", () => {
    fetch("https://example.com/beacon")
      .then(() => console.log("PROBE ASYNC http:SUCCEEDED"))
      .catch((err) => console.log("PROBE ASYNC http:" + (err.cause?.code || err.code || err.message)));
    return "INITIATED";
  });

  console.log("PROBE RESULT " + JSON.stringify(attempts));
  return attempts;
}

module.exports = { name: "untrusted-demo", exercise };

if (process.env.PROBE_RUN === "1") exercise();
