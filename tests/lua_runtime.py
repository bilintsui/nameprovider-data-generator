"""System Lua 5.1 adapter for verifying generated table values."""

import ctypes
import ctypes.util


class LuaRuntimeError(RuntimeError):
    """The required system Lua 5.1 library is missing or unusable."""


class LuaTable:
    def __init__(self, source):
        library = next((name for version in ("lua5.1", "lua-5.1", "lua51") if (name := ctypes.util.find_library(version))), None)
        if not library:
            raise LuaRuntimeError("tests require the system Lua 5.1 shared library; on Debian/Ubuntu, install liblua5.1-0")
        try:
            self.lua = ctypes.CDLL(library)
        except OSError as error:
            raise LuaRuntimeError(f"cannot load system Lua 5.1 library {library}: {error}") from error
        if not hasattr(self.lua, "lua_pcall"):
            raise LuaRuntimeError(f"{library} does not provide the Lua 5.1 API")
        signatures = {
            "luaL_newstate": (ctypes.c_void_p, []),
            "luaL_loadbuffer": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]),
            "luaL_openlibs": (None, [ctypes.c_void_p]),
            "lua_pcall": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]),
            "lua_getfield": (None, [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]),
            "lua_gettable": (None, [ctypes.c_void_p, ctypes.c_int]),
            "lua_pushlstring": (None, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]),
            "lua_rawgeti": (None, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
            "lua_type": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_int]),
            "lua_tolstring": (ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]),
            "lua_settop": (None, [ctypes.c_void_p, ctypes.c_int]),
            "lua_close": (None, [ctypes.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.lua, name)
            function.restype = result
            function.argtypes = arguments
        self.state = self.lua.luaL_newstate()
        if not self.state:
            raise MemoryError("cannot create Lua state")
        try:
            self.lua.luaL_openlibs(self.state)
            self.lua.lua_getfield(self.state, -10002, b"_VERSION")
            version = self.string()
            if version != "Lua 5.1":
                raise LuaRuntimeError(f"expected Lua 5.1, found {version}")
            self.lua.lua_settop(self.state, 0)
            if self.lua.luaL_loadbuffer(self.state, source, len(source), b"result.lua"):
                raise AssertionError(self.string())
            if self.lua.lua_pcall(self.state, 0, 1, 0):
                raise AssertionError(self.string())
        except BaseException:
            self.close()
            raise

    def string(self):
        length = ctypes.c_size_t()
        pointer = self.lua.lua_tolstring(self.state, -1, ctypes.byref(length))
        if not pointer:
            raise AssertionError("expected a Lua string")
        return ctypes.string_at(pointer, length.value).decode("utf-8")

    def field(self, key):
        encoded = key.encode("utf-8")
        self.lua.lua_pushlstring(self.state, encoded, len(encoded))
        self.lua.lua_gettable(self.state, -2)
        try:
            return self.string()
        finally:
            self.lua.lua_settop(self.state, -2)

    def row(self, key, columns):
        encoded = key.encode("utf-8")
        self.lua.lua_pushlstring(self.state, encoded, len(encoded))
        self.lua.lua_gettable(self.state, -2)
        if self.lua.lua_type(self.state, -1) != 5:
            self.lua.lua_settop(self.state, -2)
            raise AssertionError(f"expected a Lua table for {key!r}")
        values = []
        try:
            for column in range(1, columns + 1):
                self.lua.lua_rawgeti(self.state, -1, column)
                try:
                    values.append(self.string())
                finally:
                    self.lua.lua_settop(self.state, -2)
        finally:
            self.lua.lua_settop(self.state, -2)
        return values

    def close(self):
        if self.state:
            self.lua.lua_close(self.state)
            self.state = None

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        self.close()
