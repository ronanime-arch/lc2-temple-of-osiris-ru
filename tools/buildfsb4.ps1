param(
    [string]$Wav,
    [string]$Out,
    [int]$Quality = 30,
    [uint32]$Flags = 0x40,
    [int]$Version = 0
)

$here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$tools = Join-Path $here 'fsbankex_official\tools'
$lib   = Join-Path $tools 'fsbanklib\fsbanklibex.dll'
$cs    = Get-Content (Join-Path $here 'fsbank4.cs') -Raw

Add-Type -TypeDefinition $cs -Language CSharp
[Fb]::SetDllDirectory($tools) | Out-Null
[Fb]::LoadLibrary($lib) | Out-Null

if (Test-Path $Out) { Remove-Item $Out -Force }
Write-Output ([Fb]::Build($Wav, $Out, $Quality, $Flags, $Version))

if (Test-Path $Out) {
    $b = [System.IO.File]::ReadAllBytes($Out)
    $magic = [System.Text.Encoding]::ASCII.GetString($b, 0, 4)
    Write-Output ("output: " + (Get-Item $Out).Length + " bytes, magic=" + $magic)
} else {
    Write-Output "output: file was not created"
}
