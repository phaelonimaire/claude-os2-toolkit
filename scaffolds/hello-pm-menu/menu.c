/* hello-pm-menu - a PM application with a menu, a modal dialog, an accelerator table
 * and string resources. The next step up from scaffolds/hello-pm.
 *
 * Everything here was compiled and run on OS/2. The comments mark the four places a
 * Win32 habit produces code that builds cleanly and misbehaves silently.
 *
 * Build: see BUILD.md.  Reference: ../../os2ref/resources-and-dialogs.md,
 * ../../os2ref/pm-window-messaging.md, ../../recipes/porting-a-windows-app.md
 */
#define INCL_WIN
#define INCL_GPI
#include <os2.h>
#include <stdio.h>
#include <string.h>
#include "menu.h"

static CHAR  szTitle[128]  = "";
static CHAR  szStatus[128] = "Use the File menu, or Ctrl+Ins / Shift+Ins.";
static SHORT sNumber       = 42;

/*--------------------------------------------------------------------------
 * The dialog procedure.
 *------------------------------------------------------------------------*/
static MRESULT EXPENTRY NumberDlgProc(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)
{
    static SHORT *pNumber;

    switch (msg) {

    /* PM sends WM_INITDLG, not WM_CREATE. mp2 is the pCreateParams pointer given to
       WinDlgBox; mp1 is the control that will get the focus. */
    case WM_INITDLG:
        pNumber = (SHORT *)mp2;
        WinSetDlgItemShort(hwnd, IDC_NUMBER, (USHORT)*pNumber, FALSE);
        WinSendDlgItemMsg(hwnd, IDC_NUMBER, EM_SETTEXTLIMIT, MPFROMSHORT(15), 0);

        /* !! INVERTED FROM WIN32 !!  WM_INITDLG's return is a "focus set indicator":
           TRUE  = the procedure has ALREADY set the focus itself,
           FALSE = focus not changed, so PM assigns the default.
           Win32's WM_INITDIALOG means the opposite. Returning Win32's TRUE here leaves
           NO control focused: the dialog renders perfectly and ignores every key. */
        return (MRESULT)FALSE;

    case WM_COMMAND:
        switch (SHORT1FROMMP(mp1)) {

        case DID_OK: {
            SHORT s = 0;
            /* WinQueryDlgItemShort returns FALSE when the text is not a number -
               the direct equivalent of Win32 GetDlgItemInt's fTranslated flag. */
            if (WinQueryDlgItemShort(hwnd, IDC_NUMBER, &s, FALSE)) {
                *pNumber = s;
                WinDismissDlg(hwnd, DID_OK);
            } else {
                /* PM has no WM_NEXTDLGCTL; set the focus directly. */
                WinSetFocus(HWND_DESKTOP, WinWindowFromID(hwnd, IDC_NUMBER));
            }
            return (MRESULT)0;
        }

        case DID_CANCEL:
            WinDismissDlg(hwnd, DID_CANCEL);
            return (MRESULT)0;
        }
        return (MRESULT)0;
    }

    return WinDefDlgProc(hwnd, msg, mp1, mp2);
}

/*--------------------------------------------------------------------------
 * The client window.
 *------------------------------------------------------------------------*/
MRESULT EXPENTRY ClientWndProc(HWND hwnd, ULONG msg, MPARAM mp1, MPARAM mp2)
{
    switch (msg) {

    case WM_PAINT: {
        RECTL  rcl;
        POINTL ptl;
        HPS    hps = WinBeginPaint(hwnd, NULLHANDLE, &rcl);

        WinQueryWindowRect(hwnd, &rcl);
        WinFillRect(hps, &rcl, CLR_WHITE);
        GpiSetColor(hps, CLR_BLACK);

        /* Window coordinates are BOTTOM-LEFT origin: y grows upward, so "near the top"
           is rcl.yTop minus a margin. */
        ptl.x = 16;  ptl.y = rcl.yTop - 40;
        GpiCharStringAt(hps, &ptl, (LONG)strlen(szTitle), (PCH)szTitle);
        ptl.y -= 24;
        GpiCharStringAt(hps, &ptl, (LONG)strlen(szStatus), (PCH)szStatus);

        WinEndPaint(hps);
        return (MRESULT)0;
    }

    case WM_COMMAND:
        switch (SHORT1FROMMP(mp1)) {

        case IDM_SETNUMBER:
            if (WinDlgBox(HWND_DESKTOP, hwnd, NumberDlgProc, NULLHANDLE,
                          IDD_NUMBER, &sNumber) == DID_OK)
                sprintf(szStatus, "OK - number is now %d", (int)sNumber);
            else
                sprintf(szStatus, "Cancelled - number left at %d", (int)sNumber);
            WinInvalidateRect(hwnd, NULL, FALSE);
            return (MRESULT)0;

        case IDM_COPY:
            sprintf(szStatus, "Copy  (Ctrl+C or Ctrl+Ins)");
            WinInvalidateRect(hwnd, NULL, FALSE);
            return (MRESULT)0;

        case IDM_PASTE:
            sprintf(szStatus, "Paste (Ctrl+V or Shift+Ins)");
            WinInvalidateRect(hwnd, NULL, FALSE);
            return (MRESULT)0;

        case IDM_EXIT:
            WinPostMsg(hwnd, WM_QUIT, 0, 0);
            return (MRESULT)0;
        }
        break;
    }

    /* Anything not handled goes to WinDefWindowProc. For WM_CHAR in particular this is
       load-bearing: the default procedure forwards unhandled keys to the OWNER window,
       and that forwarding is what lets the frame see menu mnemonics and Tab traversal.
       Returning FALSE instead of falling through here breaks all of it silently. */
    return WinDefWindowProc(hwnd, msg, mp1, mp2);
}

/* Every PM call in main() is checked, per the kit's "fail honestly" discipline: PM
 * reports *why* through WinGetLastError, and an unchecked NULLHANDLE here surfaces
 * later as a blank window or a silent exit with no clue which call failed.
 *
 * This is a WINDOWAPI module, so stderr may not be attached to anything visible when
 * launched from the WPS - run it from a command line, or swap this for WinMessageBox()
 * once the message queue exists. */
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
    HWND  hwndFrame, hwndClient = NULLHANDLE;
    QMSG  qmsg;

    /* FCF_MENU and FCF_ACCELTABLE make WinCreateStdWindow load the MENU and ACCELTABLE
       resources whose ids match the idResources argument (ID_MAINWIN) below. */
    ULONG flFrame = FCF_TITLEBAR | FCF_SYSMENU | FCF_SIZEBORDER | FCF_MINMAX |
                    FCF_TASKLIST | FCF_MENU | FCF_ACCELTABLE;

    hab = WinInitialize(0);
    if (hab == NULLHANDLE) {
        fprintf(stderr, "WinInitialize failed\n");   /* no HAB yet: no PMERR */
        return 1;
    }

    hmq = WinCreateMsgQueue(hab, 0);
    if (hmq == NULLHANDLE)
        return fail(hab, "WinCreateMsgQueue");

    /* hmod NULLHANDLE = this .EXE's own resources. WinLoadString returns the string
       length, and 0 means Error [DOC-IBM - PM Reference, pm2.txt "WinLoadString
       Return Value - lLength"]. Unchecked, a missing string or wrong id just yields
       an empty title bar - quiet wrongness, not a failure. */
    if (WinLoadString(hab, NULLHANDLE, IDS_TITLE, sizeof(szTitle), (PSZ)szTitle) == 0)
        return fail(hab, "WinLoadString(IDS_TITLE)");

    if (!WinRegisterClass(hab, (PSZ)"HelloPmMenu", ClientWndProc, CS_SIZEREDRAW, 0))
        return fail(hab, "WinRegisterClass");

    hwndFrame = WinCreateStdWindow(HWND_DESKTOP, WS_VISIBLE, &flFrame,
                                   (PSZ)"HelloPmMenu", (PSZ)"hello-pm-menu",
                                   0, NULLHANDLE, ID_MAINWIN, &hwndClient);
    if (hwndFrame == NULLHANDLE) {
        fail(hab, "WinCreateStdWindow");
        WinDestroyMsgQueue(hmq);
        WinTerminate(hab);
        return 1;
    }

    if (!WinSetWindowPos(hwndFrame, HWND_TOP, 60, 60, 520, 200,
                         SWP_SIZE | SWP_MOVE | SWP_SHOW | SWP_ACTIVATE))
        fail(hab, "WinSetWindowPos");   /* not fatal: the window exists, carry on */

    while (WinGetMsg(hab, &qmsg, NULLHANDLE, 0, 0))
        WinDispatchMsg(hab, &qmsg);

    WinDestroyWindow(hwndFrame);
    WinDestroyMsgQueue(hmq);
    WinTerminate(hab);
    return 0;
}
