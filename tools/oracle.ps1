# Decode .fsb banks with the game's own FMOD Ex 4.33.9 runtime and report what comes out.
# Run with the 32-bit PowerShell: C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe
param([string]$Dir = "$PSScriptRoot\oracle")

$gameDir = "D:\Games\Lara Croft - Temple of Osiris\Game"

$src = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class Fm
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool SetDllDirectory(string path);

    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_Create(out IntPtr system);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_SetOutput(IntPtr system, int output);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_Init(IntPtr system, int maxchannels, uint flags, IntPtr extra);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    public static extern int FMOD_System_CreateSound(IntPtr system, string name, uint mode, IntPtr exinfo, out IntPtr sound);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Sound_GetNumSubSounds(IntPtr sound, out int num);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Sound_GetSubSound(IntPtr sound, int index, out IntPtr sub);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Sound_GetLength(IntPtr sound, out uint length, uint unit);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Sound_ReadData(IntPtr sound, byte[] buffer, uint len, out uint read);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Sound_Release(IntPtr sound);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_Release(IntPtr system);

    public const uint SOFTWARE   = 0x00000040;
    public const uint OPENONLY   = 0x00002000;
    public const uint TWOD       = 0x00000008;
    public const uint LOOPOFF    = 0x00000001;
    public const uint ACCURATE   = 0x00004000;
    public const uint UNIT_MS    = 0x00000001;
    public const uint UNIT_PCM   = 0x00000002;

    public static string Probe(IntPtr sys, string path, uint extraMode) { return Probe(sys, path, extraMode, null); }

    public static string Probe(IntPtr sys, string path, uint extraMode, string wavOut)
    {
        IntPtr snd;
        int r = FMOD_System_CreateSound(sys, path, SOFTWARE | OPENONLY | TWOD | LOOPOFF | ACCURATE | extraMode, IntPtr.Zero, out snd);
        if (r != 0) return "CreateSound FAILED, код " + r;
        IntPtr play = snd;
        int n = 0;
        FMOD_Sound_GetNumSubSounds(snd, out n);
        if (n > 0) { IntPtr sub; if (FMOD_Sound_GetSubSound(snd, 0, out sub) == 0) play = sub; }
        uint ms = 0, pcm = 0;
        FMOD_Sound_GetLength(play, out ms, UNIT_MS);
        FMOD_Sound_GetLength(play, out pcm, UNIT_PCM);

        byte[] buf = new byte[65536];
        System.IO.MemoryStream pcmOut = new System.IO.MemoryStream();
        long total = 0; double sum = 0; int peak = 0; int reads = 0; int lastErr = 0;
        while (true)
        {
            uint got;
            int rr = FMOD_Sound_ReadData(play, buf, (uint)buf.Length, out got);
            if (got > 0)
            {
                total += got;
                for (int i = 0; i + 1 < got; i += 2)
                {
                    short s = (short)(buf[i] | (buf[i + 1] << 8));
                    int a = s < 0 ? -s : s;
                    if (a > peak) peak = a;
                    sum += (double)s * s;
                }
                pcmOut.Write(buf, 0, (int)got);
                reads++;
            }
            if (rr != 0) { lastErr = rr; if (got == 0) break; }
            else if (got == 0) break;
            if (reads > 4000) break;
        }
        FMOD_Sound_Release(snd);
        if (wavOut != null)
        {
            byte[] pcm2 = pcmOut.ToArray();
            using (var fs = new System.IO.FileStream(wavOut, System.IO.FileMode.Create))
            using (var w = new System.IO.BinaryWriter(fs))
            {
                w.Write(Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + pcm2.Length);
                w.Write(Encoding.ASCII.GetBytes("WAVEfmt ")); w.Write(16); w.Write((short)1);
                w.Write((short)1); w.Write(44100); w.Write(88200); w.Write((short)2); w.Write((short)16);
                w.Write(Encoding.ASCII.GetBytes("data")); w.Write(pcm2.Length); w.Write(pcm2);
            }
        }
        long samples = total / 2;
        double rms = samples > 0 ? Math.Sqrt(sum / samples) : 0;
        return string.Format("declared {0} ms / {1} pcm | decoded {2} samples = {3:0.00} s | peak {4} | rms {5:0} | end {6}",
                             ms, pcm, samples, samples / 44100.0, peak, rms, lastErr);
    }
}
'@

Add-Type -TypeDefinition $src -Language CSharp
[Fm]::SetDllDirectory($gameDir) | Out-Null

$sys = [IntPtr]::Zero
$r = [Fm]::FMOD_System_Create([ref]$sys)
Write-Output ("System_Create: " + $r)
[Fm]::FMOD_System_SetOutput($sys, 2) | Out-Null      # NOSOUND
$r = [Fm]::FMOD_System_Init($sys, 32, 0, [IntPtr]::Zero)
Write-Output ("System_Init  : " + $r)

$CREATESTREAM = 0x00000080
foreach ($f in Get-ChildItem -Path $Dir -Filter *.fsb | Sort-Object Name) {
    Write-Output ("--- " + $f.Name)
    $wav = [System.IO.Path]::ChangeExtension($f.FullName, ".decoded.wav")
    Write-Output ("    sample: " + [Fm]::Probe($sys, $f.FullName, 0, $wav))
}
[Fm]::FMOD_System_Release($sys) | Out-Null
