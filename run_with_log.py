import sys
import subprocess
from pathlib import Path
from datetime import datetime
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Run an existing Python script and save the same console logs to a text file."
    )
    parser.add_argument(
        "script",
        nargs="?",
        default="query)v2.py",
        help="Path to the Python script to run (default: query)v2.py)",
    )
    parser.add_argument(
        "--logs-dir",
        default="logs",
        help="Directory where log files will be saved (default: logs)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding for reading/writing logs (default: utf-8)",
    )

    # Capture any additional args meant for the target script
    args, passthrough = parser.parse_known_args()

    script_path = Path(args.script).expanduser().resolve()
    if not script_path.exists():
        print(f"[ERROR] Script not found: {script_path}")
        sys.exit(1)

    logs_dir = Path(args.logs_dir).expanduser().resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{script_path.stem}_run_{timestamp}.txt"

    command = [sys.executable, str(script_path), *passthrough]

    print("=" * 72)
    print("Python Script Logger Wrapper")
    print("=" * 72)
    print(f"Target script : {script_path}")
    print(f"Log file      : {log_path}")
    print(f"Command       : {' '.join(command)}")
    print("=" * 72)
    print()

    with open(log_path, "w", encoding=args.encoding, errors="replace") as log_file:
        log_file.write("=" * 72 + "\n")
        log_file.write("Python Script Logger Wrapper\n")
        log_file.write("=" * 72 + "\n")
        log_file.write(f"Target script : {script_path}\n")
        log_file.write(f"Log file      : {log_path}\n")
        log_file.write(f"Command       : {' '.join(command)}\n")
        log_file.write("=" * 72 + "\n\n")
        log_file.flush()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            encoding=args.encoding,
            errors="replace",
        )

        try:
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="")
                log_file.write(line)
                log_file.flush()
        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user. Terminating target script...")
            log_file.write("\n[INFO] Interrupted by user. Terminating target script...\n")
            log_file.flush()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise
        finally:
            return_code = process.wait()
            summary = f"\n[INFO] Target script finished with exit code: {return_code}\n"
            print(summary, end="")
            log_file.write(summary)
            log_file.write(f"[INFO] Logs saved to: {log_path}\n")
            log_file.flush()

    print(f"[INFO] Logs saved to: {log_path}")
    sys.exit(return_code)


if __name__ == "__main__":
    main()
