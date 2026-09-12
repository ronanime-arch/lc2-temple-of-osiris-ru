# Actually PLAY each bank through the game's FMOD runtime, with the non-realtime
# wav-writer output. That mirrors the engine's playback path instead of ReadData.
param([string]$Bank)

$gameDir = "D:\Games\Lara Croft - Temple of Osiris\Game"

$src = @'
using System;
using System.Runtime.InteropServices;

public static class Fp
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    public static extern bool SetDllDirectory(string path);

    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_Create(out IntPtr system);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_SetOutput(IntPtr system, int output);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Ansi)]
    public static extern int FMOD_System_SetSoftwareFormat(IntPtr system, int rate, int format, int numoutch, int maxinch, int resamp);
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
    public static extern int FMOD_System_PlaySound(IntPtr system, int channelid, IntPtr sound, int paused, out IntPtr channel);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Channel_IsPlaying(IntPtr channel, out int isplaying);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Channel_GetPosition(IntPtr channel, out uint pos, uint unit);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_Update(IntPtr system);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_Sound_Release(IntPtr sound);
    [DllImport("fmodex.dll", CallingConvention = CallingConvention.StdCall)]
    public static extern int FMOD_System_Release(IntPtr system);

    public const uint SOFTWARE = 0x00000040;
    public const uint TWOD = 0x00000008;
    public const uint LOOPOFF = 0x00000001;
    public const uint CREATESTREAM = 0x00000080;
    public const uint UNIT_MS = 1;

    public static string Play(string path)
    {
        IntPtr sys;
        int r = FMOD_System_Create(out sys);
        if (r != 0) return "System_Create " + r;
        FMOD_System_SetOutput(sys, 5);                 // WAVWRITER_NRT
        r = FMOD_System_Init(sys, 32, 0, IntPtr.Zero);
        if (r != 0) return "System_Init " + r;

        IntPtr snd;
        r = FMOD_System_CreateSound(sys, path, SOFTWARE | TWOD | LOOPOFF | CREATESTREAM, IntPtr.Zero, out snd);
        if (r != 0) { FMOD_System_Release(sys); return "CreateSound " + r; }
        IntPtr play = snd;
        int n; FMOD_Sound_GetNumSubSounds(snd, out n);
        if (n > 0) { IntPtr sub; if (FMOD_Sound_GetSubSound(snd, 0, out sub) == 0) play = sub; }
        uint ms; FMOD_Sound_GetLength(play, out ms, UNIT_MS);

        IntPtr ch;
        r = FMOD_System_PlaySound(sys, -1, play, 0, out ch);
        if (r != 0) { FMOD_Sound_Release(snd); FMOD_System_Release(sys); return "PlaySound " + r; }

        int playing = 1, guard = 0; uint pos = 0, maxpos = 0; int stalls = 0; uint prev = 0;
        while (playing != 0 && guard < 6000)
        {
            FMOD_System_Update(sys);
            FMOD_Channel_IsPlaying(ch, out playing);
            if (FMOD_Channel_GetPosition(ch, out pos, UNIT_MS) == 0)
            {
                if (pos > maxpos) maxpos = pos;
                if (pos == prev) stalls++; else stalls = 0;
                prev = pos;
            }
            guard++;
        }
        FMOD_Sound_Release(snd);
        FMOD_System_Release(sys);
        return string.Format("declared {0} ms | played up to {1} ms | update cycles {2} | repeated-position cycles {3}",
                             ms, maxpos, guard, stalls);
    }
}
'@

Add-Type -TypeDefinition $src -Language CSharp
[Fp]::SetDllDirectory($gameDir) | Out-Null

$files = if ($Bank) { @(Get-Item $Bank) } else { Get-ChildItem "$PSScriptRoot\oracle" -Filter *.fsb | Sort-Object Name }
foreach ($f in $files) {
    $out = Join-Path $PSScriptRoot ("played_" + [System.IO.Path]::GetFileNameWithoutExtension($f.Name) + ".wav")
    if (Test-Path "$PSScriptRoot\fmodoutput.wav") { Remove-Item "$PSScriptRoot\fmodoutput.wav" -Force }
    Push-Location $PSScriptRoot
    $res = [Fp]::Play($f.FullName)
    Pop-Location
    if (Test-Path "$PSScriptRoot\fmodoutput.wav") { Move-Item "$PSScriptRoot\fmodoutput.wav" $out -Force }
    $sz = if (Test-Path $out) { (Get-Item $out).Length } else { 0 }
    Write-Output ("--- " + $f.Name)
    Write-Output ("    " + $res + " | wav " + $sz + " bytes")
}
