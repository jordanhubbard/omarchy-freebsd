/*
 * Run a desktop session and clean up after it, the FreeBSD counterpart of
 * systemd stopping a session's scope at logout.
 *
 * The helper becomes a reaper (procctl(2) PROC_REAP_ACQUIRE), so every process
 * started in the session stays its descendant even after its own parent exits.
 * It runs the command, forwards SIGHUP, SIGINT and SIGTERM to it, and once the
 * command exits sends SIGTERM to everything left, then SIGKILL to whatever is
 * still running after a grace period. It exits with the command's status.
 *
 * usage: session-reaper command [args...]
 */

#include <sys/types.h>
#include <sys/procctl.h>
#include <sys/wait.h>

#include <err.h>
#include <errno.h>
#include <signal.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define GRACE_MS	3000

static volatile sig_atomic_t child_pid;

static void
forward(int sig)
{
	if (child_pid > 0)
		kill(child_pid, sig);
}

static int
descendants(void)
{
	struct procctl_reaper_status rs;

	if (procctl(P_PID, getpid(), PROC_REAP_STATUS, &rs) == -1)
		return (0);
	return ((int)rs.rs_descendants);
}

static void
reap_all(void)
{
	while (waitpid(-1, NULL, WNOHANG) > 0)
		;
}

static void
kill_descendants(int sig)
{
	struct procctl_reaper_kill rk;

	memset(&rk, 0, sizeof(rk));
	rk.rk_sig = sig;
	(void)procctl(P_PID, getpid(), PROC_REAP_KILL, &rk);
}

int
main(int argc, char *argv[])
{
	struct sigaction sa;
	struct timespec pause = { 0, 50 * 1000 * 1000 };
	pid_t pid;
	int status, waited;

	if (argc < 2)
		errx(2, "usage: session-reaper command [args...]");
	if (procctl(P_PID, getpid(), PROC_REAP_ACQUIRE, NULL) == -1)
		err(1, "procctl(PROC_REAP_ACQUIRE)");

	memset(&sa, 0, sizeof(sa));
	sa.sa_handler = forward;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGHUP, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);
	sigaction(SIGTERM, &sa, NULL);

	if ((pid = fork()) == -1)
		err(1, "fork");
	if (pid == 0) {
		signal(SIGHUP, SIG_DFL);
		signal(SIGINT, SIG_DFL);
		signal(SIGTERM, SIG_DFL);
		execvp(argv[1], argv + 1);
		err(127, "%s", argv[1]);
	}
	child_pid = pid;

	/* Wait for the session command, reaping orphans adopted meanwhile. */
	for (;;) {
		pid_t done = waitpid(-1, &status, 0);

		if (done == pid)
			break;
		if (done == -1 && errno != EINTR)
			err(1, "waitpid");
	}
	child_pid = 0;

	kill_descendants(SIGTERM);
	for (waited = 0; descendants() > 0 && waited < GRACE_MS; waited += 50) {
		reap_all();
		nanosleep(&pause, NULL);
	}
	if (descendants() > 0) {
		kill_descendants(SIGKILL);
		while (descendants() > 0 && waitpid(-1, NULL, 0) > 0)
			;
	}
	reap_all();

	if (WIFEXITED(status))
		return (WEXITSTATUS(status));
	return (128 + WTERMSIG(status));
}
