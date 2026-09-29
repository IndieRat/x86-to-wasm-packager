typedef unsigned int u32;
typedef unsigned char u8;

typedef u32 (__attribute__((cdecl)) *malloc_fn)(u32);
typedef u32 (__attribute__((cdecl)) *free_fn)(u32);
typedef u32 (__attribute__((cdecl)) *strlen_fn)(u32);
typedef u32 (__attribute__((cdecl)) *fs_mount_fn)(u32,u32,u32);
typedef u32 (__attribute__((cdecl)) *fs_open_fn)(u32,u32,u32);
typedef u32 (__attribute__((cdecl)) *fs_read_fn)(u32,u32,u32);
typedef u32 (__attribute__((cdecl)) *fs_close_fn)(u32);
typedef u32 (__attribute__((cdecl)) *reg_create_fn)(u32,u32,u32);
typedef u32 (__attribute__((cdecl)) *reg_set_fn)(u32,u32,u32,u32,u32);
typedef u32 (__attribute__((cdecl)) *reg_close_fn)(u32);

#define XWASM_MALLOC    ((malloc_fn)0x70010000u)
#define XWASM_FREE      ((free_fn)0x70010004u)
#define XWASM_STRLEN    ((strlen_fn)0x70010008u)
#define XWASM_FS_MOUNT  ((fs_mount_fn)0x7001000Cu)
#define XWASM_FS_OPEN   ((fs_open_fn)0x70010010u)
#define XWASM_FS_READ   ((fs_read_fn)0x70010014u)
#define XWASM_FS_CLOSE  ((fs_close_fn)0x70010018u)
#define XWASM_REG_CREATE ((reg_create_fn)0x7001001Cu)
#define XWASM_REG_SET    ((reg_set_fn)0x70010020u)
#define XWASM_REG_CLOSE  ((reg_close_fn)0x70010024u)

#define HKEY_CURRENT_USER 0x80000001u
#define REG_DWORD 4u

static char fs_path[] = "saves/c5.dat";
static char fs_data[] = "C5!";
static char fs_output[8];
static char reg_path[] = "Software/C5/Runtime";
static char reg_name[] = "Milestone";
static u32 reg_value = 0x000000C5u;

int main(void) {
    u32 scratch = XWASM_MALLOC(16);
    scratch = scratch;
    ((u8 *)scratch)[0] = 'C';
    ((u8 *)scratch)[1] = '5';
    ((u8 *)scratch)[2] = 0;

    u32 length = XWASM_STRLEN(scratch);
    XWASM_FREE(scratch);

    u32 mount_result = XWASM_FS_MOUNT((u32)fs_path, (u32)fs_data, 3);
    u32 handle = XWASM_FS_OPEN((u32)fs_path, 1, 0);
    u32 read_result = XWASM_FS_READ(handle, (u32)fs_output, 3);
    XWASM_FS_CLOSE(handle);

    u32 key = 0;
    XWASM_REG_CREATE(HKEY_CURRENT_USER, (u32)reg_path, (u32)&key);
    XWASM_REG_SET(key, (u32)reg_name, REG_DWORD, (u32)&reg_value, 4);
    XWASM_REG_CLOSE(key);

    mount_result = mount_result;
    read_result = read_result;
    return length;
}
