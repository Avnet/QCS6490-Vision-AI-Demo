import re
import subprocess
import threading

from vai.common import HW_SAMPLING_PERIOD_ms

# NOTE: Its expected that you have QProf installed on your device with the necessary exports/pathing enabled as well
# refer to QC documentation as necessary


class QProfProcess(threading.Thread):
    """Run the Qualcomm profiler and extract metrics of interest"""

    def __init__(self):
        self.enabled = True
        self.CPU = 0
        self.GPU = 0
        self.MEM = 0
        threading.Thread.__init__(self)

    def run(self):
        """Run a qprof subprocess until the thread is disabled via Close()."""

        ansi_escape_8bit = re.compile(
            rb"(?:\x1B[@-Z\\-_]|[\x80-\x9A\x9C-\x9F]|(?:\x1B\[|\x9B)[0-?]*[ -/]*[@-~])"
        )
        while self.enabled:
            p = subprocess.Popen(
                f"qprof \
                                    --profile \
                                    --profile-type async \
                                    --result-format CSV \
                                    --capabilities-list profiler:apps-proc-cpu-metrics profiler:proc-gpu-specific-metrics profiler:apps-proc-mem-metrics \
                                    --profile-time 10 \
                                    --sampling-rate {HW_SAMPLING_PERIOD_ms} \
                                    --streaming-rate {HW_SAMPLING_PERIOD_ms} \
                                    --live \
                                    --metric-id-list 4648 4616 4865".split(),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            while self.enabled:
                # line = p.stdout.readline().decode('utf-8').encode("ascii","ignore")
                line = p.stdout.readline().decode("utf-8").encode("ascii", "ignore")

                line = ansi_escape_8bit.sub(b"", line)
                if not line:
                    break
                # the real code does filtering here

                if line.find(b"CPU Total Load:") > -1:
                    result = re.search(b"CPU Total Load:(.*)%", line)
                    self.CPU = float(result.group(1))
                elif line.find(b"GPU Utilization:") > -1:
                    result = re.search(b"GPU Utilization:(.*)%", line)
                    self.GPU = float(result.group(1))
                elif line.find(b"Memory Usage %:") > -1:
                    result = re.search(b"Memory Usage %:(.*)%", line)
                    self.MEM = float(result.group(1))

            # cleanup output files
            subprocess.call(
                "/bin/rm -rf /data/shared/QualcommProfiler/profilingresults/*",
                shell=True,
            )

    def Close(self):
        self.enabled = False

    def get_cpu_usage_pct(self):
        return round(self.CPU, 2)

    def get_gpu_usage_pct(self):
        return round(self.GPU, 2)

    def get_memory_usage_pct(self):
        return round(self.MEM, 2)
