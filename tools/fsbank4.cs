using System;
using System.Runtime.InteropServices;

public static class Fb
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    public static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr LoadLibrary(string path);

    [DllImport("fsbanklibex.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    public static extern int FSBank_Init(int version, uint flags, uint numJobs, string cacheDir);
    [DllImport("fsbanklibex.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    public static extern int FSBank_Build(IntPtr subSounds, uint numSubSounds, int format, uint buildFlags, uint quality, string encryptKey, string outputFileName);
    [DllImport("fsbanklibex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FSBank_Release();

    // version: 0 = FSBANK_FSBVERSION_FSB4, 1 = FSB5
    // format : 4 = FSBANK_FORMAT_MP3
    public static string Build(string wav, string outFsb, int quality, uint flags, int version)
    {
        int r = FSBank_Init(version, 0, 1, null);
        if (r != 0) return "FSBank_Init failed: " + r;

        IntPtr nameStr = Marshal.StringToHGlobalAnsi(wav);
        IntPtr nameList = Marshal.AllocHGlobal(IntPtr.Size);
        Marshal.WriteIntPtr(nameList, 0, nameStr);

        int sz = IntPtr.Size + 4 * 6;
        IntPtr sub = Marshal.AllocHGlobal(sz);
        for (int i = 0; i < sz; i++) Marshal.WriteByte(sub, i, 0);
        Marshal.WriteIntPtr(sub, 0, nameList);
        Marshal.WriteInt32(sub, IntPtr.Size, 1);

        int rb = FSBank_Build(sub, 1, 4, flags, (uint)quality, null, outFsb);
        int rr = FSBank_Release();

        Marshal.FreeHGlobal(sub);
        Marshal.FreeHGlobal(nameList);
        Marshal.FreeHGlobal(nameStr);
        return "Init=0 Build=" + rb + " Release=" + rr;
    }
}
