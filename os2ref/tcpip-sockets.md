# OS/2 TCP/IP Sockets API

The BSD-derived sockets programming interface that OS/2 TCP/IP exports to applications:
`socket`, `bind`, `listen`, `accept`, `connect`, the `send`/`recv` and `sendto`/`recvfrom`
families, `select`, socket-option and name query calls, and the address structures they share.
It is a Berkeley 4.4-style API — the OS/2 Toolkit ships the Berkeley `sys/socket.h`,
`netinet/in.h`, and `netdb.h` almost verbatim — with a small set of OS/2-specific additions
(`sock_init`, `soclose`, `so_cancel`, `os2_ioctl`, `os2_select`, `sock_errno`/`psock_errno`) that
exist because an OS/2 socket is **not** a Control Program file handle and cannot be reached through
`DosRead`/`DosWrite`/`DosClose`. Every entry point uses the `_System` (`APIENTRY`) linkage. A
descriptor is a plain `int` returned by `socket()` or `accept()`; addresses are carried in
`struct sockaddr_in` (internet) cast to the generic `struct sockaddr`; and multi-byte address and
port values travel in **network byte order** (big-endian), for which the `htons`/`htonl` /
`ntohs`/`ntohl` conversions are provided.

Provenance: **[DOC-IBM]** OS/2 Toolkit 4.5 TCP/IP headers — `sys/socket.h` (call prototypes,
`SOCK_*`, `AF_*`/`PF_*`, `SO_*`, `MSG_*`, `struct sockaddr`/`msghdr`/`linger`), `netinet/in.h`
(`struct sockaddr_in`/`in_addr`, `IPPROTO_*`, `INADDR_*`, `sin_*`), `netdb.h`
(`gethostbyname`/`getservbyname` and `struct hostent`/`servent`/`protoent`), `unistd.h`
(`soclose`, `select`, `os2_select`), `sys/ioctl.h` + `sys/sockio.h` + `sys/filio.h`
(`ioctl`/`os2_ioctl`, `SIOC*`, `FIONBIO`), `types.h` (`fd_set`, `FD_*` — the 32-bit `_System` API), `arpa/inet.h`
(`inet_addr`/`inet_ntoa`), `sys/itypes.h` and `pmwsock.h` (byte-order macros/prototypes),
`nerrno.h` (`SOCE*` error codes). **[DOC-IBM]** the IBM TCP/IP Toolkit `SAMPLES/TCPIPTK/SOCKET`
programs (`tcpc.c`, `tcps.c`, `udpc.c`, `selects.c`) and `OS2IOCTL/os2ioctl.c` for canonical call
sequences. **[DOC]** *TCP/IP Programming for OS/2* (IBM) for behavioural detail (`sock_init`
requirement, `select` timeout semantics) the headers do not carry.

---

## 1. Function map [DOC-IBM — `sys/socket.h`, `unistd.h`, `netdb.h`, `arpa/inet.h`, `sys/ioctl.h`]

### 1.1 Core socket calls [DOC-IBM — `sys/socket.h`]

| Function | Prototype | Purpose |
|---|---|---|
| `socket` | `int socket(int domain, int type, int protocol)` | Create a socket; returns a descriptor or `-1` |
| `bind` | `int bind(int s, const struct sockaddr *name, int namelen)` | Bind a local address/port to a socket |
| `listen` | `int listen(int s, int backlog)` | Mark a stream socket as accepting connections |
| `accept` | `int accept(int s, struct sockaddr *addr, int *addrlen)` | Accept a connection; returns a new connected descriptor |
| `connect` | `int connect(int s, const struct sockaddr *name, int namelen)` | Connect a socket to a remote address |
| `send` | `ssize_t send(int s, const void *buf, size_t len, int flags)` | Send on a connected socket |
| `recv` | `ssize_t recv(int s, void *buf, size_t len, int flags)` | Receive on a connected socket |
| `sendto` | `ssize_t sendto(int s, const void *buf, size_t len, int flags, const struct sockaddr *to, int tolen)` | Send a datagram to an explicit address |
| `recvfrom` | `ssize_t recvfrom(int s, void *buf, size_t len, int flags, struct sockaddr *from, int *fromlen)` | Receive a datagram, reporting the sender's address |
| `sendmsg` | `ssize_t sendmsg(int s, const struct msghdr *msg, int flags)` | Scatter/gather send with optional ancillary data |
| `recvmsg` | `ssize_t recvmsg(int s, struct msghdr *msg, int flags)` | Scatter/gather receive with optional ancillary data |
| `getpeername` | `int getpeername(int s, struct sockaddr *name, int *namelen)` | Report the remote address of a connected socket |
| `getsockname` | `int getsockname(int s, struct sockaddr *name, int *namelen)` | Report the local address bound to a socket |
| `getsockopt` | `int getsockopt(int s, int level, int optname, void *optval, int *optlen)` | Read a socket option |
| `setsockopt` | `int setsockopt(int s, int level, int optname, const void *optval, int optlen)` | Set a socket option |
| `shutdown` | `int shutdown(int s, int how)` | Shut down part or all of a full-duplex connection |
| `socketpair` | `int socketpair(int domain, int type, int protocol, int *sv)` | Create a connected pair of sockets |

### 1.2 OS/2-specific additions [DOC-IBM — `sys/socket.h`, `unistd.h`, `sys/ioctl.h`]

| Function | Prototype | Purpose |
|---|---|---|
| `sock_init` | `int sock_init(void)` | Initialize the socket library for the process; returns `0` on success |
| `soclose` | `int soclose(int s)` | **Close a socket** (the socket-space equivalent of `DosClose`) |
| `so_cancel` | `int so_cancel(int s)` | Cancel outstanding blocking calls on a socket |
| `soabort` | `int soabort(int s)` | Abort a socket, discarding any pending data |
| `os2_ioctl` | `int os2_ioctl(int s, unsigned long cmd, char *data, int len)` | Socket control; explicit-length OS/2 form of `ioctl` |
| `ioctl` | `int ioctl(int s, unsigned long cmd, ...)` | BSD-style socket control (length implied by `cmd` encoding) |
| `os2_select` | `int os2_select(int *sockets, int nrd, int nwr, int nex, long timeout)` | Array-of-sockets select with millisecond timeout |
| `select` | `int select(int nfds, fd_set *rd, fd_set *wr, fd_set *ex, struct timeval *tv)` | BSD `fd_set`-based readiness multiplexing |
| `sock_errno` | `int sock_errno(void)` | Return the last socket error (an `SOCE*` value) for the calling thread |
| `psock_errno` | `void psock_errno(const char *string)` | Print `string` plus the text of the last socket error |
| `sock_strerror` | `char *sock_strerror(int errno)` | Map an `SOCE*` code to its message text |
| `getinetversion` | `int getinetversion(char *)` | Query the installed TCP/IP stack version |
| `addsockettolist` | `void addsockettolist(int s)` | Register a socket in the process's socket list (see §2) |
| `removesocketfromlist` | `int removesocketfromlist(int s)` | Remove a socket from the process's socket list |

### 1.3 Name / address resolution [DOC-IBM — `netdb.h`, `arpa/inet.h`]

| Function | Prototype | Purpose |
|---|---|---|
| `gethostbyname` | `struct hostent *gethostbyname(const char *name)` | Resolve a host name to address(es) |
| `gethostbyaddr` | `struct hostent *gethostbyaddr(const char *addr, int len, int type)` | Reverse-resolve an address to a host name |
| `getservbyname` | `struct servent *getservbyname(const char *name, const char *proto)` | Look up a service by name (e.g. `"ftp"`, `"tcp"`) |
| `getservbyport` | `struct servent *getservbyport(int port, const char *proto)` | Look up a service by port number |
| `getprotobyname` | `struct protoent *getprotobyname(const char *name)` | Look up a protocol by name |
| `gethostname` | `int gethostname(char *name, int namelen)` | Return the local host's name (`unistd.h`) |
| `inet_addr` | `unsigned long inet_addr(const char *cp)` | Parse dotted-decimal text to a network-order address |
| `inet_ntoa` | `char *inet_ntoa(struct in_addr in)` | Format a network-order address as dotted-decimal text |
| `inet_network` | `unsigned long inet_network(const char *cp)` | Parse dotted-decimal text to a network number |

`h_errno` (a per-thread value, `netdb.h` defines it as `(*tcp_h_errno1())`) carries the resolver
error after a failed `gethost*` call, taking one of `HOST_NOT_FOUND` (1), `TRY_AGAIN` (2),
`NO_RECOVERY` (3), `NO_DATA`/`NO_ADDRESS` (4), or `NETDB_INTERNAL` (-1) [DOC-IBM `netdb.h:121-127`].
The name-database files live under `\MPTN\ETC` (`hosts`, `services`, `protocols`, `networks`,
`hosts.equiv`) [DOC-IBM `netdb.h:70-74`].

---

## 2. The socket handle model — a socket is not a file handle [DOC-IBM / DOC]

A socket descriptor is a small `int`, returned by `socket()` or `accept()`, that names an entry in
a **separate descriptor space** owned by the TCP/IP socket library and its transport driver — not
the Control Program file-handle (`HFILE`) space. The evidence is structural in the API itself:

- A socket is closed with **`soclose(s)`**, a dedicated call [DOC-IBM `unistd.h:46`], not with
  `DosClose`. Every Toolkit sample opens with `socket()`/`accept()` and closes with `soclose()`
  (`tcpc.c`, `tcps.c`, `udpc.c`) [DOC-IBM].
- Control is done with **`ioctl`/`os2_ioctl`** [DOC-IBM `sys/ioctl.h:61,65`], not `DosDevIOCtl`,
  and errors are read with **`sock_errno()`** [DOC-IBM `sys/socket.h:383`] returning the biased
  `SOCE*` codes (§8), a namespace disjoint from the Control Program `ERROR_*` space.
- The socket library keeps a **per-process socket list**; `addsockettolist()` /
  `removesocketfromlist()` register and deregister descriptors in it [DOC-IBM
  `sys/socket.h:389-390`]. This list is what lets the library find and clean up a process's sockets
  independently of the file system.

Before any socket call, a process must call **`sock_init()`** once; it initializes the library's
connection to the transport (`INET.SYS`) and returns `0` on success — a non-zero result indicates
the stack is not running [DOC — *TCP/IP Programming for OS/2*; DOC-IBM `selects.c` checks
`sock_init() != 0` → "INET.SYS probably is not running"]. All Toolkit samples call `sock_init()`
first [DOC-IBM `tcpc.c:60`, `tcps.c:62`, `udpc.c:56`].

`fd_set` is correspondingly **not** a bitmask of file descriptors but a counted array of socket
numbers [DOC-IBM `types.h:105-118` — `FD_SETSIZE`=64 @105, `struct fd_set` @109-112, `__TCPFDIsSet` @118]:

```c
#pragma pack(4)
typedef struct fd_set {
        u_short fd_count;               /* how many are set */
        int     fd_array[FD_SETSIZE];   /* an array of sockets */
} fd_set;
#pragma pack()
#define FD_SETSIZE 64                   /* default; user-overridable */
```

`FD_ZERO`, `FD_SET`, `FD_CLR`, and `FD_ISSET` operate on that array (the last via the helper
`__TCPFDIsSet`) [DOC-IBM `types.h:122-144`].

---

## 3. Creating a socket — `socket(domain, type, protocol)`

### 3.1 Address / protocol family (`domain`) [DOC-IBM `sys/socket.h:102-140`]

The internet family is `AF_INET`; the matching protocol-family constant `PF_INET` has the same
value and either spelling is used interchangeably in practice (samples pass `PF_INET` to `socket()`
and store `AF_INET` in `sin_family`) [DOC-IBM `tcpc.c:86,93`].

| Constant | Value | Meaning |
|---|---|---|
| `AF_UNSPEC` | `0` | Unspecified |
| `AF_LOCAL` / `AF_UNIX` / `AF_OS2` | `1` | Local (pipes) |
| `AF_INET` | `2` | Internet: TCP, UDP, etc. |
| `AF_OS2` | `AF_UNIX` (`1`) | OS/2 local family alias |
| `AF_NB` / `AF_NETBIOS` | `17` | NetBIOS |
| `AF_INET6` | `24` | IPv6 |
| `AF_MAX` | `45` | One past the last defined family |

`PF_*` mirror the `AF_*` values one-for-one (`PF_INET == AF_INET`, `PF_MAX == AF_MAX`) [DOC-IBM
`sys/socket.h:164-197`].

### 3.2 Socket `type` [DOC-IBM `sys/socket.h:49-53`]

| Constant | Value | Meaning |
|---|---|---|
| `SOCK_STREAM` | `1` | Reliable, connection-oriented byte stream (TCP) |
| `SOCK_DGRAM` | `2` | Connectionless datagrams (UDP) |
| `SOCK_RAW` | `3` | Raw protocol access |
| `SOCK_RDM` | `4` | Reliably-delivered message |
| `SOCK_SEQPACKET` | `5` | Sequenced packet stream |

### 3.3 `protocol` [DOC-IBM `netinet/in.h:50-64`]

`0` selects the default protocol for the type (TCP for `SOCK_STREAM`, UDP for `SOCK_DGRAM`).
Explicit values come from the `IPPROTO_*` set: `IPPROTO_IP` (0), `IPPROTO_ICMP` (1), `IPPROTO_IGMP`
(2), `IPPROTO_TCP` (6), `IPPROTO_UDP` (17), `IPPROTO_RAW` (255), among others.

---

## 4. Address structures [DOC-IBM — `netinet/in.h`, `sys/socket.h`]

### 4.1 `struct sockaddr` — the generic form [DOC-IBM `sys/socket.h:146-150`]

Passed (by cast) to every call that takes an address. It is a length + family header followed by
family-specific bytes.

| Field | Type | Meaning |
|---|---|---|
| `sa_len` | `u_char` | Total length of the address |
| `sa_family` | `u_char` | Address family (`AF_*`) |
| `sa_data` | `char[14]` | Family-specific address value (nominal; longer in practice) |

### 4.2 `struct sockaddr_in` — the internet form [DOC-IBM `netinet/in.h:132-140`]

Byte-for-byte overlays `struct sockaddr` for `AF_INET`. The header packs it to byte alignment
(`#pragma pack(1)`).

| Field | Type | Meaning |
|---|---|---|
| `sin_len` | `u_char` | Length of this address |
| `sin_family` | `u_char` | `AF_INET` |
| `sin_port` | `u_short` | Port, **network byte order** |
| `sin_addr` | `struct in_addr` | IP address, **network byte order** |
| `sin_zero` | `char[8]` | Padding to the size of `struct sockaddr`; set to zero |

### 4.3 `struct in_addr` [DOC-IBM `netinet/in.h:82-84`]

```c
struct in_addr {
        u_long s_addr;                  /* 32-bit IP address, network byte order */
};
```

Well-known address values [DOC-IBM `netinet/in.h:117-127`]: `INADDR_ANY` (`0x00000000`, "bind to
all local interfaces"), `INADDR_BROADCAST` (`0xffffffff`), `INADDR_NONE` (`0xffffffff`, the
`inet_addr` failure return), and `IN_LOOPBACKNET` (`127`). A server fills `sin_addr.s_addr =
INADDR_ANY` before `bind` [DOC-IBM `tcps.c:83`]; a client fills it from a resolved address or
`inet_addr()` [DOC-IBM `tcpc.c:88`, `udpc.c:71`].

---

## 5. Byte order — `htons` / `htonl` / `ntohs` / `ntohl` [DOC-IBM]

Ports and addresses are stored and transmitted in **network (big-endian) byte order**; on the
little-endian x86 host the application must convert host values before placing them in a
`sockaddr_in` and convert back after reading one. The four conversions are provided both as macros
and as callable functions:

| Symbol | Signature | Purpose |
|---|---|---|
| `htons` | `u_short htons(u_short)` | Host → network, 16-bit (ports) |
| `ntohs` | `u_short ntohs(u_short)` | Network → host, 16-bit |
| `htonl` | `u_long htonl(u_long)` | Host → network, 32-bit (addresses) |
| `ntohl` | `u_long ntohl(u_long)` | Network → host, 32-bit |

The macro forms expand to byte-swap primitives — `htons`/`ntohs` to `_bswap` (16-bit swap),
`htonl`/`ntohl` to `_lswap` (32-bit swap) [DOC-IBM `sys/itypes.h:123-126`]; the function-prototype
forms are declared in `pmwsock.h` (`APIENTRY htonl`/`htons`/`ntohl`/`ntohs`) [DOC-IBM
`pmwsock.h:670-682`]. Toolkit code applies `htons(port)` when filling `sin_port` [DOC-IBM
`tcpc.c:87`, `tcps.c:82`].

---

## 6. Socket options — `getsockopt` / `setsockopt` [DOC-IBM `sys/socket.h`]

Options are addressed by a `level` and an `optname`. The socket level is `SOL_SOCKET`
(`0xffff`) [DOC-IBM `sys/socket.h:97`]; IP-level options use `level = IPPROTO_IP` with the
`IP_*` names from `netinet/in.h`.

Per-socket `SO_*` options [DOC-IBM `sys/socket.h:58-84`]:

| Constant | Value | Meaning |
|---|---|---|
| `SO_DEBUG` | `0x0001` | Record debugging information |
| `SO_ACCEPTCONN` | `0x0002` | Socket has done `listen()` (query) |
| `SO_REUSEADDR` | `0x0004` | Allow reuse of a local address |
| `SO_KEEPALIVE` | `0x0008` | Keep connections alive |
| `SO_DONTROUTE` | `0x0010` | Bypass routing, use interface directly |
| `SO_BROADCAST` | `0x0020` | Permit sending broadcast datagrams |
| `SO_USELOOPBACK` | `0x0040` | Bypass hardware where possible |
| `SO_LINGER` | `0x0080` | Linger on close while data remains (see `struct linger`) |
| `SO_OOBINLINE` | `0x0100` | Deliver out-of-band data in line |
| `SO_REUSEPORT` | `0x1000` | Allow reuse of local address and port |
| `SO_SNDBUF` | `0x1001` | Send buffer size |
| `SO_RCVBUF` | `0x1002` | Receive buffer size |
| `SO_SNDLOWAT` / `SO_RCVLOWAT` | `0x1003` / `0x1004` | Send / receive low-water marks |
| `SO_SNDTIMEO` / `SO_RCVTIMEO` | `0x1005` / `0x1006` | Send / receive timeouts |
| `SO_ERROR` | `0x1007` | Read and clear the pending error |
| `SO_TYPE` | `0x1008` | Read the socket type |

`struct linger` (for `SO_LINGER`) [DOC-IBM `sys/socket.h:89-92`]:

| Field | Type | Meaning |
|---|---|---|
| `l_onoff` | `long_int` | Linger on/off |
| `l_linger` | `long_int` | Linger time, seconds |

---

## 7. `send`/`recv` flags, `shutdown`, and `ioctl`

### 7.1 Message flags [DOC-IBM `sys/socket.h:278-291`]

OR'd into the `flags` argument of the send/recv family:

| Constant | Value | Meaning |
|---|---|---|
| `MSG_OOB` | `0x1` | Out-of-band data |
| `MSG_PEEK` | `0x2` | Peek without consuming |
| `MSG_DONTROUTE` | `0x4` | Send bypassing routing |
| `MSG_FULLREAD` | `0x8` | Read the full request |
| `MSG_EOR` | `0x10` | Data completes a record |
| `MSG_TRUNC` | `0x20` | Datagram was truncated on receive |
| `MSG_WAITALL` | `0x80` | Wait for the full request |
| `MSG_DONTWAIT` | `0x100` | Non-blocking for this call |

### 7.2 `shutdown(s, how)`

`how` selects which directions to close: `0` = further receives disallowed, `1` = further sends
disallowed, `2` = both. (The socket layer records these as the `SO_RCV_SHUTDOWN` `0x0400` /
`SO_SND_SHUTDOWN` `0x0800` internal state flags [DOC-IBM `sys/socket.h:68-69`].) The descriptor is
still released only by `soclose`.

### 7.3 `ioctl` / `os2_ioctl` commands [DOC-IBM `sys/filio.h`, `sys/sockio.h`]

`ioctl(s, cmd, argp)` encodes the argument size and direction in `cmd` (the `_IOR`/`_IOW`/`_IOWR`
macros of `sys/ioccom.h`); `os2_ioctl(s, cmd, data, len)` passes the length explicitly and is used
for variable-length results [DOC-IBM `os2ioctl.c:147`].

| Command | Encoding | Purpose |
|---|---|---|
| `FIONREAD` | `_IOR('f',127,int)` | Bytes available to read |
| `FIONBIO` | `_IOW('f',126,int)` | Set/clear non-blocking mode |
| `FIOASYNC` | `_IOW('f',125,int)` | Set/clear asynchronous I/O |
| `SIOCATMARK` | `_IOR('s',7,int)` | At the out-of-band mark? |
| `SIOCGIFADDR` | `_IOWR('i',33,struct ifreq)` | Get an interface address |
| `SIOCGIFCONF` | `_IOWR('i',36,struct ifconf)` | Enumerate interfaces |
| `SIOCGIFFLAGS` | `_IOWR('i',17,struct ifreq)` | Get interface flags |

(`sys/sockio.h` defines the full `SIOC*` interface/route set; the rows above are representative.
The header is guarded so it is used only with the 32-bit stack, not the older 16-bit `TCPV40HDRS`
build [DOC-IBM `sys/sockio.h:39-41`].)

---

## 8. Readiness multiplexing — `select` and `os2_select`

Two forms coexist [DOC-IBM `unistd.h:57-58`]:

- **`os2_select(int *sockets, int nrd, int nwr, int nex, long timeout)`** — the OS/2-native form.
  `sockets` points to a flat array holding the read-check descriptors first, then the write-check,
  then the except-check; `nrd`/`nwr`/`nex` give the counts of each group; `timeout` is in
  **milliseconds**. On return the array entries that are not ready are set to `-1` and the function
  returns the number ready. *TCP/IP Programming for OS/2* shows this form (an array of sockets, a
  read count of 1, and an 18000 ms timeout) invoked to wait up to 18 seconds for a response
  [DOC — *TCP/IP Programming for OS/2* §FTP client; the prototype is header-confirmed
  (`unistd.h:57`) but the array/`-1`/count-ready convention is book-described, not header-defined.
  Note the Toolkit `selects.c` sample uses the BSD `select()` form (a `timeval`), not `os2_select`].
- **`select(int nfds, fd_set *readfds, fd_set *writefds, fd_set *exceptfds, struct timeval *tv)`** —
  the BSD form over the counted-array `fd_set` (§2). A `NULL` `tv` blocks indefinitely; a zero
  `timeval` polls.

---

## 9. Name resolution structures [DOC-IBM — `netdb.h`]

`gethostbyname`/`gethostbyaddr` return a pointer to a static `struct hostent`; addresses come back
in **network order**, ready to copy into `sin_addr` [DOC-IBM `netdb.h:81`, and `tcpc.c:88` copies
`*(unsigned long *)hostnm->h_addr` into `sin_addr.s_addr`].

`struct hostent` [DOC-IBM `netdb.h:83-90`]:

| Field | Type | Meaning |
|---|---|---|
| `h_name` | `char *` | Official host name |
| `h_aliases` | `char **` | NULL-terminated alias list |
| `h_addrtype` | `int` | Address family (`AF_INET`) |
| `h_length` | `int` | Address length in bytes |
| `h_addr_list` | `char **` | NULL-terminated address list; `h_addr` = `h_addr_list[0]` |

`struct servent` [DOC-IBM `netdb.h:103-108`]:

| Field | Type | Meaning |
|---|---|---|
| `s_name` | `char *` | Official service name |
| `s_aliases` | `char **` | Alias list |
| `s_port` | `int` | Port number, **network order** |
| `s_proto` | `char *` | Protocol name (`"tcp"`/`"udp"`) |

`struct protoent` carries `p_name`, `p_aliases`, `p_proto` (protocol number) [DOC-IBM
`netdb.h:110-114`].

---

## 10. Error codes — `sock_errno()` and the `SOCE*` space [DOC-IBM — `nerrno.h`]

Socket errors are **not** Control Program `ERROR_*` values. They are BSD `errno` values biased by
`SOCBASEERR` (`10000` in user space) so they cannot collide with the C runtime's `errno`
[DOC-IBM `nerrno.h:15-19`]. A call returns `-1` and the code is retrieved with `sock_errno()`;
`psock_errno("tag")` prints the tag and message. Common values (`SOCBASEERR + n`):

| Constant | Value | Meaning |
|---|---|---|
| `SOCEINTR` | `10004` | Interrupted call |
| `SOCEBADF` | `10009` | Bad socket descriptor |
| `SOCEACCES` | `10013` | Permission denied |
| `SOCEFAULT` | `10014` | Bad address |
| `SOCEINVAL` | `10022` | Invalid argument |
| `SOCEMFILE` | `10024` | Too many open sockets |
| `SOCEWOULDBLOCK` / `SOCEAGAIN` | `10035` | Operation would block (non-blocking socket) |
| `SOCEINPROGRESS` | `10036` | Operation now in progress |
| `SOCEALREADY` | `10037` | Operation already in progress |
| `SOCENOTSOCK` | `10038` | Operation on a non-socket |
| `SOCEDESTADDRREQ` | `10039` | Destination address required |
| `SOCEMSGSIZE` | `10040` | Message too long |
| `SOCEPROTOTYPE` | `10041` | Wrong protocol type for socket |
| `SOCEPROTONOSUPPORT` | `10043` | Protocol not supported |
| `SOCEAFNOSUPPORT` | `10047` | Address family not supported |
| `SOCEADDRINUSE` | `10048` | Address already in use |
| `SOCEADDRNOTAVAIL` | `10049` | Cannot assign requested address |
| `SOCENETDOWN` | `10050` | Network is down |
| `SOCENETUNREACH` | `10051` | Network is unreachable |
| `SOCECONNABORTED` | `10053` | Connection aborted locally |
| `SOCECONNRESET` | `10054` | Connection reset by peer |
| `SOCENOBUFS` | `10055` | No buffer space available |
| `SOCEISCONN` | `10056` | Socket is already connected |
| `SOCENOTCONN` | `10057` | Socket is not connected |
| `SOCESHUTDOWN` | `10058` | Cannot send after shutdown |
| `SOCETIMEDOUT` | `10060` | Connection timed out |
| `SOCECONNREFUSED` | `10061` | Connection refused |
| `SOCEHOSTUNREACH` | `10065` | No route to host |
| `SOCEOS2ERR` | `10100` | Underlying OS/2 error (also `SOCELAST`) |

For source portability, `nerrno.h` also defines the plain BSD spellings (`EWOULDBLOCK`,
`ECONNRESET`, …) as aliases of the corresponding `SOCE*` value when not already defined [DOC-IBM
`nerrno.h:128-318`].

---

## 11. Canonical call sequences [DOC-IBM — Toolkit `SAMPLES/TCPIPTK/SOCKET`]

**TCP server** [DOC-IBM `tcps.c`]:
`sock_init()` → `socket(PF_INET, SOCK_STREAM, 0)` → fill `sockaddr_in` (`sin_family = AF_INET`,
`sin_port = htons(port)`, `sin_addr.s_addr = INADDR_ANY`) → `bind` → `listen(s, backlog)` →
`accept(s, &client, &namelen)` (returns the connected descriptor `ns`) → `recv`/`send` on `ns` →
`soclose(ns)` and `soclose(s)`.

**TCP client** [DOC-IBM `tcpc.c`]:
`sock_init()` → `gethostbyname(host)` → fill `sockaddr_in` (`sin_addr` from `h_addr`,
`sin_port = htons(port)`) → `socket(PF_INET, SOCK_STREAM, 0)` → `connect(s, &server, sizeof server)`
→ `send`/`recv` → `soclose(s)`.

**UDP client** [DOC-IBM `udpc.c`]:
`sock_init()` → `socket(PF_INET, SOCK_DGRAM, 0)` → fill `sockaddr_in` (`sin_addr` from
`inet_addr(text)`, `sin_port = htons(port)`) → `sendto(s, buf, len, 0, &server, sizeof server)` →
`soclose(s)`. A datagram server correspondingly uses `recvfrom` to learn the sender's address.

---

## Sources opened
- `README.md`, `file-io.md` — house style.
- `SYS/socket.h` — call prototypes, `SOCK_*`, `AF_*`/`PF_*`, `SO_*`,
  `MSG_*`, `SOL_SOCKET`, `SOMAXCONN`, `struct sockaddr`/`msghdr`/`linger`, OS/2 additions
  (`sock_init`, `so_cancel`, `soabort`, `sock_errno`, `psock_errno`, `sock_strerror`,
  `addsockettolist`/`removesocketfromlist`, `getinetversion`).
- `NETINET/in.h` — `struct sockaddr_in`/`in_addr`, `IPPROTO_*`,
  `INADDR_*`, `IN_LOOPBACKNET`, `IP_*`.
- `netdb.h` — `struct hostent`/`servent`/`protoent`/`netent`,
  `gethostby*`/`getservby*`/`getprotoby*`, `h_errno`, `NETDB_*`/`HOST_NOT_FOUND` codes,
  `\MPTN\ETC` database paths.
- `unistd.h` — `soclose`, `select`, `os2_select`, `gethostname`.
- `SYS/ioctl.h`, `SYS/sockio.h`, `SYS/filio.h` — `ioctl`/`os2_ioctl`,
  `SIOC*`, `FIONREAD`/`FIONBIO`/`FIOASYNC`.
- `types.h` (`fd_set`, `FD_SETSIZE`, `FD_*` for the 32-bit `_System` API).
- `ARPA/inet.h` — `inet_addr`/`inet_ntoa`/`inet_network`/`inet_aton`.
- `SYS/itypes.h`, `pmwsock.h` — `htons`/`htonl`/`ntohs`/`ntohl`.
- `nerrno.h` — `SOCE*` error codes and BSD aliases.
- `Toolkit sample TCPIPTK/SOCKET/tcpc.c`, `tcps.c`, `udpc.c`, `selects.c`;
  `SAMPLES/TCPIPTK/OS2IOCTL/os2ioctl.c` — canonical call sequences and `os2_ioctl` usage.
- *TCP/IP Programming for OS/2* (IBM) — `sock_init` requirement, `select`/`soclose` behavioural
  detail.
</content>
</invoke>
