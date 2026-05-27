import os
import threading

class FdFilter:
    """
    Redirects low-level file descriptors (stdout, stderr) to a pipe,
    filters the output in a separate thread, and writes the filtered
    output back to the original destination. This is necessary to
    suppress messages from C libraries that write directly to file
    descriptors, bypassing sys.stdout/sys.stderr.
    """
    def __init__(self, filter_strings):
        self.filter_strings = [s.lower() for s in filter_strings]
        self.original_stdout_fd = os.dup(1)
        self.original_stderr_fd = os.dup(2)

        # Create pipes to intercept stdout and stderr
        self.stdout_pipe_r, self.stdout_pipe_w = os.pipe()
        self.stderr_pipe_r, self.stderr_pipe_w = os.pipe()

        # Redirect stdout and stderr to the write-ends of the pipes
        os.dup2(self.stdout_pipe_w, 1)
        os.dup2(self.stderr_pipe_w, 2)

        # Create threads to read from the pipes, filter, and write to original FDs
        self.stdout_thread = threading.Thread(target=self._pipe_reader, args=(self.stdout_pipe_r, self.original_stdout_fd))
        self.stderr_thread = threading.Thread(target=self._pipe_reader, args=(self.stderr_pipe_r, self.original_stderr_fd))
        #daemon thread will be terminated when application or process exits
        self.stdout_thread.daemon = True
        self.stderr_thread.daemon = True
        self.stdout_thread.start()
        self.stderr_thread.start()

    def _pipe_reader(self, pipe_r_fd, original_dest_fd):
        """Reads from a pipe, filters, and writes to the destination."""
        with os.fdopen(pipe_r_fd, 'r') as pipe_file:
            for line in iter(pipe_file.readline, ''):
                if not any(f in line.lower() for f in self.filter_strings):
                    os.write(original_dest_fd, line.encode('utf-8'))

