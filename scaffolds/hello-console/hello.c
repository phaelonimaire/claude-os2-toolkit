/* hello-console - a minimal OS/2 text-mode program.
 *
 * The .def marks it WINDOWCOMPAT, so it runs in a VIO window (or full screen).
 * This deliberately uses plain C stdio, which is all most console programs
 * need; VioWrtTTY below shows the OS/2-native path for when you need direct
 * screen control (cursor placement, attributes, full-screen output) - see
 * os2ref/vio-kbd-mou.md.
 *
 * Build: see BUILD.md.
 */
#define INCL_DOS
#define INCL_VIO
#include <os2.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv)
{
    static const char msg[] = "...and the same line via VioWrtTTY.\r\n";

    printf("Hello from an OS/2 console app.\n");
    if (argc > 1)
        printf("You passed %d argument(s); the first is \"%s\".\n", argc - 1, argv[1]);
    fflush(stdout);          /* stdio and Vio* are separate output paths */

    /* APIRET16 APIENTRY16 VioWrtTTY(PCH pch, USHORT cb, HVIO hvio);
     *   [DOC-IBM: Toolkit 4.5 bsesub.h - see os2ref/vio-kbd-mou.md section 2.2]
     * hvio is 0 for the caller's own session. Note APIRET16 (USHORT), not the
     * 32-bit APIRET: the Vio family is a 16-bit API. 0 == success. */
    {
        APIRET16 rc = VioWrtTTY((PCH)msg, (USHORT)strlen(msg), 0);
        if (rc != 0) {
            fprintf(stderr, "VioWrtTTY failed, rc=%u\n", (unsigned)rc);
            return 1;
        }
    }
    return 0;
}
