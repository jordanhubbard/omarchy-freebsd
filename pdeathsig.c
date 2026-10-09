/*
 * Run a command that receives a signal when its parent exits, the FreeBSD
 * counterpart of setpriv --pdeathsig (procctl(2) PROC_PDEATHSIG_CTL).
 *
 * usage: pdeathsig SIGNAL command [args...]
 */

#include <sys/types.h>
#include <sys/procctl.h>

#include <err.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

static int
parse_signal(const char *name)
{
	char *end;
	long number;
	int i;

	number = strtol(name, &end, 10);
	if (*name != '\0' && *end == '\0' && number > 0 && number < NSIG)
		return ((int)number);
	if (strncasecmp(name, "SIG", 3) == 0)
		name += 3;
	for (i = 1; i < NSIG; i++)
		if (sys_signame[i] != NULL && strcasecmp(name, sys_signame[i]) == 0)
			return (i);
	return (-1);
}

int
main(int argc, char *argv[])
{
	pid_t parent;
	int sig;

	if (argc < 3)
		errx(2, "usage: pdeathsig SIGNAL command [args...]");
	if ((sig = parse_signal(argv[1])) < 0)
		errx(2, "unknown signal: %s", argv[1]);

	parent = getppid();
	if (procctl(P_PID, 0, PROC_PDEATHSIG_CTL, &sig) == -1)
		err(1, "procctl");
	/* The parent may have exited before the request took effect. */
	if (getppid() != parent)
		raise(sig);

	execvp(argv[2], argv + 2);
	err(127, "%s", argv[2]);
}
