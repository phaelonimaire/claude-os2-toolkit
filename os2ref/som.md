# The System Object Model (SOM)

The **System Object Model** is OS/2's language-neutral, binary object model - the foundation
the Workplace Shell and other object-oriented subsystems are built on. SOM lets a class be
*implemented* in one programming language and *used* from another, and (crucially for a shipped
operating system) lets a class library evolve - add methods, add instance data, insert a new
parent - without forcing client binaries to recompile. This is achieved by separating a class's
**interface** (described in an IDL file) from its **implementation** (written in C, C++, or
another language), and by resolving methods through a per-class **method table** at run time
rather than by fixed compiled-in offsets. A small **SOM runtime** (`SOMObject`, `SOMClass`,
`SOMClassMgr`, and a set of C-callable procedures) provides the object model; the **SOM Compiler**
turns `.idl` files into language bindings and implementation templates.

This reference covers the object model and the *core runtime* - the three primitive classes, the
object lifecycle, the three method-resolution mechanisms, IDs, class registration, and the
compiler/binding model. It does not enumerate every method of `SOMObject`/`SOMClass`; it describes
the architecture and a representative set of the important calls.

Provenance: **[DOC-IBM]** IBM *System Object Model Programming Reference* (`somref`, "SOM Kernel
Reference") and IBM *System Object Model Programming Guide* (`somguide`), both from the SOMobjects
Base Toolkit. Symbols, prototypes, and struct fields **[DOC-IBM]** confirmed against the OS/2
Toolkit 4.5 SOM headers under `SOM/INCLUDE` (`sombtype.h`, `somapi.h`, `somobj.h`,
`somcls.xh`, `somcm.xh`, `somltype.h`, `somcdev.h`), cited `file:line`. IBM canonical spellings
throughout.

---

## 1. The object model - three primitive classes [DOC-IBM]

In SOM, **classes are themselves objects**. A class has methods and an interface and is itself
described by another class; it is therefore called a **class object**. The class that defines the
implementation of a class object is its **metaclass**: just as an instance of an ordinary class is
an object, an instance of a metaclass is a class object, and a metaclass defines the methods a
class object responds to (e.g. "create an instance of yourself"). *(somguide, "In the SOM run
time, classes are themselves objects...")*

Three primitive classes are the basis for everything else *(somguide, "The SOM system contains
three primitive classes...")*:

| Class | Role |
|---|---|
| `SOMObject` | The root ancestor of **all** SOM classes. Defines the generic behaviour every object has (initialize, free, query class, dispatch, dump). |
| `SOMClass` | The root ancestor of **all** SOM **metaclasses**. Defines the behaviour every *class object* has - manufacturing instances, and querying/updating class and method information at run time. |
| `SOMClassMgr` | The class of the single `SOMClassMgrObject`, created automatically at SOM initialization, which maintains the registry of existing classes and drives dynamic class loading/unloading. |

The key structural fact - the "3-tier" relationship - is that **`SOMClass` is itself a subclass of
`SOMObject`** *(somguide, "SOMClass is defined as a subclass (or child) of SOMObject...")*. Because a
metaclass derives (ultimately) from `SOMClass`, which derives from `SOMObject`, an instance of a
metaclass is a genuine object that also possesses all the generic `SOMObject` behaviour - which is
why it is a *class object* rather than "just a class." Every ordinary class object is an instance
of `SOMClass` (or of a metaclass derived from it); every ordinary object is an instance of a class
derived from `SOMObject`.

```
        SOMObject   <- root of all objects (instance behaviour)
          ^   ^
          |   +-------- SOMClass   <- root of all metaclasses (class-object behaviour)
          |                 ^
   (your class)      (your metaclass, if any)
      instances          instances = class objects
```

An object's representation begins with a pointer to its **instance method table** (mtab); the SOM
runtime uses this to recognize an object and to resolve its methods. `somIsObj()` tests validity
precisely on this basis - "the first word of a SOM object is a pointer to its method table"
(`somapi.h`, `somIsObj`).

### Language neutrality

To be usable across languages, a class's **interface is defined separately from its
implementation** *(somguide)*. The interface - class name, parent name(s), attributes, and method
signatures - is written in **SOM IDL** (section 6). The implementation - the method procedures - is
written in an ordinary programming language. A client can use a class implemented in a different
language, without knowing how it was implemented.

---

## 2. Core types [DOC-IBM]

All SOM runtime entry points use **`SOMLINK`** linkage, which on OS/2 is `_System` (`somltype.h:64`,
`#define SOMLINK _System`); `SOMEXTERN` is `extern`/`extern "C"` (`somltype.h:48`). The
foundational typedefs are in `sombtype.h`:

| Type | Definition | Purpose |
|---|---|---|
| `somMethodProc` | `void* SOMLINK somMethodProc(void*)` (`sombtype.h:40`) | Generic type of a method-procedure entry point. Resolution functions return one of these, to be cast to the real signature. |
| `somId` | `char **` (`sombtype.h:61`) | A **registered string identifier** - a pointer to a canonical, interned copy of a string (a method name, class name, etc.). Comparing two `somId`s is a pointer/quick compare, not a `strcmp`. |
| `somToken` | `void *` (`sombtype.h:62`) | An uninterpreted opaque value. |
| `somMToken` | `somToken` (`somapi.h:94`) | A **method token** - the run-time key that identifies a method within a method table (used by offset resolution). |
| `somDToken` | `somToken` (`somapi.h:95`) | A **data token** - identifies an instance-variable location within an object. |
| `somMethodTabs` | (method-table pointer array) | An object's/class's set of instance method tables, used by parent resolution. |
| `integer4` / `boolean` / `string` | `long` / `unsigned char` (`sombtype.h:55,67`) / `char *` (`somcorba.h:41`) | CORBA-style scalar aliases used in signatures. |

A **method token** is the constant that a class publishes for each of its static methods; offset
resolution (section 4) uses it to index the method table. Method tokens for a class `C` are held in that
class's generated **ClassData** structure (e.g. `CClassData.methodName`) and can also be obtained
at run time from a class object via `somGetMethodToken` *(somguide, "Method tokens are available
from class objects...")*.

---

## 3. Object lifecycle - creation, initialization, destruction [DOC-IBM]

### Creation

`somNew` and `somNewNoInit` are **methods on the class object** (introduced by `SOMClass`):

```c
SOMObject * SOMLINK somNew(SOMClass *somSelf);        /* somcls.xh:295 */
SOMObject * SOMLINK somNewNoInit(SOMClass *somSelf);  /* somcls.xh:297 */
```

Both allocate enough space for a new instance of the receiving class and create the instance;
`somNew` additionally invokes `somDefaultInit` on the new object, while `somNewNoInit` does **not**
initialize it *(somref, "The somNew and somNewNoInit methods create a new instance of the
receiving class...")*. If the receiver is `SOMClass` (or a class derived from it), the new object is
itself a class object; otherwise it is an ordinary object.

For C and C++ clients the usage bindings wrap this in convenience macros: the generated
`<className>New()` macro verifies the class object exists (creating it and its ancestors/metaclass
on demand), then invokes `somNew` on it *(somguide, "the <className>New macro invokes the somNew
method on the class object...")*. `<className>Renew(buf)` creates the object in caller-supplied
storage. The C++ `new` operator instead invokes `somNewNoInit` and then runs a C++ constructor
that calls an initializer *(somguide)*. The runtime-level equivalents for `SOMObject` itself are
the macros `SOMObjectNew()` / `SOMObjectRenew(buf)` (`somobj.h:230,237`).

### Initialization

`SOMObject` publishes initializer method tokens in its ClassData structure, in this order:
`somInit`, `somUninit`, `somFree`, ... `somDefaultInit`, `somDestruct` (`somobj.h:177-198`).

- **`somDefaultInit`** is the modern default initializer, invoked automatically by `somNew`. A
  class initializes its instance variables by overriding `somDefaultInit`
  (`somobj.h:246-258`, `somMD_SOMObject_somDefaultInit`).
- **`somInit`** (`somInit(SOMObject*)`, `somobj.h:505`) is the **obsolete** original initializer,
  still supported; the header explicitly directs: *"Obsolete but still supported. Override
  somDefaultInit instead of somInit."* (`somobj.h:509`).

### Destruction

- **`somUninit`** - releases resources held by an object's instance variables (the counterpart of
  `somInit`/`somDefaultInit`), without freeing the object's storage.
- **`somFree`** - `somFree(SOMObject*)` (`somobj.h:528`) uninitializes the object and releases its
  storage. This is the normal way a client disposes of an object created by `somNew`.

The generic query methods every object inherits from `SOMObject` include **`somGetClass`** (returns
the receiver's class object; *"typically not overridden"*, somref), `somGetClassName`, `somIsA` /
`somIsInstanceOf` (class-membership tests), `somRespondsTo` (does the object support a given
method), and `somPrintSelf` / `somDumpSelf` (the standard debug output overridden per class).

---

## 4. Method invocation and the three resolution mechanisms [DOC-IBM]

SOM decouples *what method to call* from *how the call site finds it*. A SOM object can be accessed
by three forms of method resolution, chosen to map onto the object models of different languages
*(somguide, "A SOM object can potentially be accessed with three different forms of method
resolution")*:

### (a) Offset (static) resolution - fast, the default

Roughly equivalent to a C++ virtual function. The method is a fixed part of the object's interface
(a **static method**), found by indexing the object's instance method table with the method's
**method token**. Best performance. The primitive is:

```c
somMethodProc * SOMLINK somResolve(SOMObject *obj, somMToken mdata);   /* somapi.h:263 */
```

It returns a pointer to the procedure implementing method `mdata` for `obj`, to be cast to the
method's real signature and called *(somref, "This function returns a pointer to the procedure
that implements the specified method...can only be used...for a static method")*. Related offset
primitives (`somapi.h:263-278`):

| Function | Resolves from | Use |
|---|---|---|
| `somResolve(obj, mtoken)` | the class of `obj` | ordinary static invocation |
| `somClassResolve(cls, mtoken)` | the **instance method table of the passed class** `cls` | *casted* resolution - call the version defined by a specific class (`somapi.h:269`; somguide) |
| `somParentResolve(parentMtabs, mtoken)` | a parent's method table | invoke a **parent** method (used by generated `..._parent_...` override code) |
| `somClassResolve` / `somResolveTerminal` / `somPCallResolve` / `somAncestorResolve` | various | specialized casted/ancestor resolution |

For C/C++ clients this is normally hidden behind the generated method-invocation macros. The
**`SOM_Resolve(obj, className, methodName)`** macro constructs the method token from the class and
method names and calls `somResolve`, expanding to the method procedure's entry-point address so it
can be cached in a variable for repeated calls *(somref, "The SOM_Resolve macro invokes the
somResolve function...")*.

### (b) Name-lookup resolution - dynamic by string

Used when the introducing class or the method token is not known at compile time. The runtime
procedure:

```c
somMethodProc * SOMLINK somResolveByName(SOMObject *obj, char *methodName);  /* somapi.h:277 */
```

returns the procedure for the named method by looking it up in the object's class *(somguide, "the
procedure somResolveByName can be used to obtain a method procedure using name-lookup
resolution")*. At the class-object level, `SOMClass` provides the query methods that back this:

```c
boolean SOMLINK somFindMethod(SOMClass *somSelf, somId methodId, somMethodProc **m);   /* somcls.xh:414 */
boolean SOMLINK somFindMethodOk(SOMClass *somSelf, somId methodId, somMethodProc **m); /* somcls.xh:418 */
boolean SOMLINK somSupportsMethod(SOMClass *somSelf, somId methodId);                  /* somcls.xh:438 */
```

`somFindMethod` reports whether the class supports the method and returns its procedure via the
out-pointer; the returned boolean distinguishes methods that can be invoked by a normal offset
call from those that require `somDispatch`. `somFindMethodOk` raises an error rather than returning
`FALSE` if the method is unsupported.

### (c) Dispatch-function resolution - fully dynamic, most encapsulated

A SOM-unique mechanism: the receiving object's class decides, by arbitrary rules, how to resolve
and invoke a method. Highest encapsulation, some performance cost. Introduced by `SOMObject`/
`SOMClass`:

```c
boolean SOMLINK somDispatch(SOMObject *somSelf, somToken *retValue, somId methodId, va_list ap);      /* somobj.h:718 */
boolean SOMLINK somClassDispatch(SOMObject *somSelf, SOMClass *clsObj, somToken *retValue, somId methodId, va_list ap);  /* somobj.h:808 */
```

Both perform method resolution and then **invoke** the selected procedure on the arguments carried
in the `va_list` (the first of which is the *target object*). `somDispatch` resolves using the
class of the receiver; `somClassDispatch` resolves using an explicitly supplied class. They make no
assumption about the return type, so they can invoke methods returning structures, and they
supersede the older type-specific `somDispatchV/L/A/D` variants *(somref, "somDispatch and
somClassDispatch perform method resolution to select a method procedure, and then invoke this
procedure on args...")*. This is the path used to invoke a method that is not known until run time or
for which no usage bindings are available *(somguide, "The somDispatch method...can be used to invoke
some other method...when usage bindings...are not available")*.

A fourth, lower-level runtime primitive, **`somApply`** (`somapi.h:521`), invokes an "apply stub"
and is the mechanism SOM itself uses to actually enter a method procedure with a `va_list`; users
call it via the dispatch methods rather than directly *(somref, "Apply stubs are never invoked
directly by SOM users. The somApply function must be used instead.")*.

---

## 5. `somId` - registered string identifiers [DOC-IBM]

Method names, class names, and attribute names are handled as **`somId`s** (`char **`,
`sombtype.h:61`): pointers to a single canonical registered copy of the string. This makes name
comparison a fast pointer/quick check and gives dispatch/name-lookup a stable key. The **String
Manager** runtime (`somapi.h:321-346`):

| Function | Purpose |
|---|---|
| `somId somIdFromString(string s)` | Create a `somId` for a string (caller frees with `SOMFree`) |
| `string somStringFromId(somId id)` (`somapi.h:333`) | Recover the C string for an id |
| `somId somCheckId(somId id)` (`somapi.h:321`) | Ensure the id is registered and in normal form; returns it |
| `int somRegisterId(somId id)` (`somapi.h:325`) | Like `somCheckId`, but returns 1 (true) on the *first* registration of the string, else 0 |
| `int somCompareIds(somId a, somId b)` | Compare two ids (1 = equal) |
| `unsigned long somTotalRegIds(void)` / `void somSetExpectedIds(unsigned long)` | Count of registered ids / hint the runtime for sizing |

---

## 6. SOM IDL and the SOM Compiler [DOC-IBM]

Implementing a SOM class is a two-file, three-step process *(somguide, "defining interface and
implementation requires two completely separate steps (plus an intervening compile)")*:

1. **Write the interface** in a `.idl` source file. An `interface` statement names the class and
   its parent(s) and declares its **attributes** (instance variables for which "get"/"set" methods
   are generated automatically) and the **signatures** of its new methods (name, argument types
   and order, return type). Inherited methods are implicit.
2. **Run the SOM Compiler** (`sc` on OS/2/AIX; `somc` on Windows) on the `.idl` file. The compiler
   runs a set of **emitters** - selected by an environment variable or command line - to produce,
   for the target language:
   - an **implementation template file** (`.c` for C, `.cpp` for C++ on OS/2) containing **stub
     method procedures** the implementor fills in;
   - **binding header files** (below).
3. **Fill in the method procedures** in the template, in the language of choice, then compile and
   link with an ordinary language compiler.

### The generated binding files [DOC-IBM]

*(somguide, "the binding files include two language-specific header files..."; the file-extension
table, somguide section "Header file...")*

| Extension | Kind | Included by | Language |
|---|---|---|---|
| `.h` | **Usage** bindings (public interface - invocation macros, `New`/`Renew`, `<class>NewClass`) | client programs | C |
| `.xh` | Usage bindings | client programs | C++ |
| `.ih` | **Implementation** bindings (internal - instance-variable access, `<class>_parent_...` parent-call macros, ClassData) | the implementation template file | C |
| `.xih` | Implementation bindings | the C++ template file | C++ |

A C client `#include`s `<classFileStem>.h`; a C++ client includes `.xh`. Usage-binding headers
transitively include the bindings they depend on. A client that does not know at compile time which
classes it will use can simply include `somobj.h` (C) or `somobj.xh` (C++) and drive objects
through name-lookup/dispatch resolution *(somguide)*. The usage bindings provide the
`_methodName(obj, args...)` invocation macro (the *short form*) and the unambiguous *long form*
`className_methodName(obj, args...)` for when two included classes share a method name *(somguide)*.

### Class initialization - the `*NewClass` function and `somInitClass`

Each class's bindings supply a static-linkage **`<className>NewClass(major, minor)`** function that
creates the class object (and its ancestors and metaclass) if needed *(somguide, "The C and C++
usage bindings...provide static linkage to a <className>NewClass function")*. The runtime prototype
for the root case is `SOMObjectNewClass(integer4 major, integer4 minor)` (`somobj.h:170`). At the
metaclass level, `SOMClass` introduces **`somInitClass`** (`somcls.xh:317`), the method that builds
a class object - assigning method tokens, laying out the instance method table and instance data -
during class creation.

---

## 7. Class registration and dynamic loading - `SOMClassMgr` [DOC-IBM]

The single `SOMClassMgrObject` (created at initialization) is a registry of all class objects and
the engine for dynamic class loading. `SOMClassMgr` introduces (`somcm.xh:89-110`):

| Method | Purpose |
|---|---|
| `somFindClass(classId, major, minor)` | Return the class object for a class, **loading its DLL if necessary** (dynamic class loading) |
| `somFindClsInFile(classId, major, minor, file)` | As above, from a named class-library file |
| `somClassFromId(classId)` (`somcm.xh:91`) | Return an already-registered class object for an id, or NULL |
| `somRegisterClass(classObj)` (`somcm.xh:92`) | Enter a class object into the registry (somref, `somRegisterClass(receiver, classObj)`) |
| `somUnregisterClass(classObj)` | Remove a class from the registry |
| `somLocateClassFile(classId, major, minor)` (`somcm.xh:94`) | Determine the file name of the DLL implementing a class |
| `somLoadClassFile(classId, major, minor, file)` (`somcm.xh:95`) | Load a class from a specific file |
| `somGetInitFunction()` (`somcm.xh:97`) | The name of a class library's initialization entry point |

### Class libraries and `SOMInitModule`

A SOM class library is a DLL that packages one or more classes. Each library supplies an
**`SOMInitModule`** entry point whose job is to create (via `*NewClass`) the class objects the
library provides. The library also identifies itself to the SOM Kernel via the `SOM_ClassLibrary`
macro. *"Typically, the SOM Kernel invokes the SOMInitModule function of each statically loaded
class library during the execution of the `somMainProgram` function... For dynamically loaded class
libraries, SOMInitModule is invoked immediately upon completion of the library's... OS/2 DLL
'init/term' function."* *(somref, SOM_ClassLibrary - Remarks; the entry point is referenced as
`SOMInitModule` in `somcdev.h:183`.)* The runtime variable `SOMClassInitFuncName` (`somapi.h:802`,
type `somTD_SOMClassInitFuncName`) names the default class-init function a library exports.

---

## 8. Runtime environment and utilities [DOC-IBM]

The SOM runtime must be initialized before objects are created; this happens automatically on first
object (or class object) creation, or explicitly:

| Function | Purpose |
|---|---|
| `SOMClassMgr * somEnvironmentNew(void)` (`somapi.h:300`) | Create/initialize the SOM environment; returns the `SOMClassMgrObject`. Idempotent - may be called repeatedly, and is called automatically when the first object is created. |
| `SOMClassMgr * somMainProgram(void)` (`somapi.h:85`) | Establishes the SOM run time for a main program and triggers the deferred `SOMInitModule` execution of statically-linked class libraries. |
| `int somPrintf(string fmt, ...)` (`somapi.h:773`) | SOM's portable formatted-output routine (with `somVprintf`, `somPrefixLevel`, `somLPrintf` companions). Used by `somPrintSelf`/`somDumpSelf` so debug output is emitted through one redirectable path. |

**Memory** is routed through replaceable procedure variables so an application can substitute its
own allocator: `SOMMalloc`, `SOMFree`, `SOMCalloc`, `SOMRealloc` (`somapi.h:807-813`; typedefs
`somTD_SOMMalloc`/`somTD_SOMFree` at `somapi.h:65,70`). Objects created by `somNew` are freed with
`somFree`; strings returned by the String Manager and storage from `SOMMalloc` are released with
`SOMFree`.

---

## 9. Putting it together - the shape of a call [DOC-IBM]

A representative client sequence, in model terms:

1. The SOM environment comes up (implicitly on first use, or via `somEnvironmentNew` /
   `somMainProgram`), creating the `SOMClassMgrObject`.
2. A class object is obtained - created eagerly by the generated `<class>New()` macro's call to
   `<class>NewClass`, or on demand by `SOMClassMgr::somFindClass` (which loads the class's DLL and
   runs its `SOMInitModule`).
3. An instance is created with `somNew` (which allocates, then runs `somDefaultInit`).
4. A method is invoked - the compiler-generated `_method(obj, ...)` macro performs **offset
   resolution** via `somResolve`/`SOM_Resolve` for speed; or, when the method is not known until
   run time, the client uses **name-lookup** (`somResolveByName`/`somFindMethod`) or **dispatch**
   (`somDispatch`) resolution.
5. The object is disposed with `somFree` (running `somUninit`, then releasing storage).

Throughout, names are carried as registered `somId`s, and every invocation path bottoms out at a
`somMethodProc` selected from the object's instance method table - which is exactly what lets a
class library add methods or instance data and insert parents without breaking already-compiled
clients.

## See also
- `wps-classes.md` - the Workplace Shell class hierarchy (`WPObject`...), the primary body of SOM classes and the `wp*` method model.
