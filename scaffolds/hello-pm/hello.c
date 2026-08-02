/* hello-pm - a minimal OS/2 Presentation Manager application.
 *
 * The canonical PM skeleton: an anchor block (HAB) and a per-thread message
 * queue, a registered window class, a standard frame + client window, the
 * get/dispatch message loop, and a window procedure that paints a string and
 * closes cleanly.  The .def marks it WINDOWAPI (a PM GUI app).
 *
 * Build: see BUILD.md.
 * Reference: os2ref/pm-window-messaging.md (the model), os2ref/gpi-drawing.md
 * (painting).  Verify any flag/prototype against the Toolkit headers.
 */
#define INCL_WIN
#define INCL_GPI
#include <os2.h>
#include <stdio.h>

#define CLS_CLIENT "HelloClient"

MRESULT EXPENTRY ClientWndProc(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)
{
    switch (msg) {
    case WM_PAINT: {
        HPS   hps = WinBeginPaint(hwnd, NULLHANDLE, NULL);
        RECTL rcl;
        WinQueryWindowRect(hwnd, &rcl);
        WinFillRect(hps, &rcl, SYSCLR_WINDOW);
        /* No DT_TEXTATTRS: that flag tells WinDrawText to take colours from the
         * PS's current attributes and IGNORE the two colour arguments, so
         * passing colours alongside it is a silent contradiction. Pass the
         * colours OR set them on the PS and use DT_TEXTATTRS - not both. */
        WinDrawText(hps, -1, "Hello, Presentation Manager", &rcl,
                    CLR_NEUTRAL, CLR_BACKGROUND,
                    DT_CENTER | DT_VCENTER);
        WinEndPaint(hps);
        return (MRESULT)FALSE;
    }
    case WM_ERASEBACKGROUND:
        /* Returning TRUE lets WM_PAINT do the fill (avoids flicker). */
        return (MRESULT)TRUE;
    }
    return WinDefWindowProc(hwnd, msg, mp1, mp2);
}

/* Every PM call below is checked. This is the kit's "fail honestly" discipline
 * applied to the smallest possible program: PM reports *why* through
 * WinGetLastError, and an unchecked NULLHANDLE here surfaces later as a blank
 * window or a silent exit with no clue which call failed.
 *
 * Note this is a WINDOWAPI (PM) module, so stderr may not be attached to
 * anything visible when launched from the WPS - run it from a command line, or
 * swap this for WinMessageBox() once the message queue exists. */
static int fail(HAB hab, const char *what)
{
    fprintf(stderr, "%s failed, PMERR=0x%04lx\n",
            what, (unsigned long)WinGetLastError(hab) & 0xFFFF);
    return 1;
}

int main(void)
{
    HAB   hab;
    HMQ   hmq;
    QMSG  qmsg;
    HWND  hwndFrame, hwndClient;
    ULONG flFrame = FCF_TITLEBAR | FCF_SYSMENU | FCF_SIZEBORDER |
                    FCF_MINMAX  | FCF_SHELLPOSITION | FCF_TASKLIST;

    hab = WinInitialize(0);
    if (hab == NULLHANDLE) {
        fprintf(stderr, "WinInitialize failed\n");   /* no HAB yet: no PMERR */
        return 1;
    }

    hmq = WinCreateMsgQueue(hab, 0);
    if (hmq == NULLHANDLE)
        return fail(hab, "WinCreateMsgQueue");

    if (!WinRegisterClass(hab, CLS_CLIENT, ClientWndProc, CS_SIZEREDRAW, 0))
        return fail(hab, "WinRegisterClass");

    hwndFrame = WinCreateStdWindow(HWND_DESKTOP, WS_VISIBLE, &flFrame,
                                   CLS_CLIENT, "Hello PM", 0, NULLHANDLE,
                                   0, &hwndClient);
    if (hwndFrame == NULLHANDLE)
        return fail(hab, "WinCreateStdWindow");

    while (WinGetMsg(hab, &qmsg, NULLHANDLE, 0, 0))
        WinDispatchMsg(hab, &qmsg);

    WinDestroyWindow(hwndFrame);
    WinDestroyMsgQueue(hmq);
    WinTerminate(hab);
    return 0;
}
