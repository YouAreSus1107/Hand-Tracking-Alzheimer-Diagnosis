# press_test.ps1 - live FSR readout for build gate 3 (docs/GLOVE_FIRMWARE_PLAN.md)
#
# Shows the raw ADC value, a bar, and the running min/max span while you press
# the sensor. The span is what you record for the gate: it tells you how much
# of the ADC range your actual finger force uses.
#
#   powershell -ExecutionPolicy Bypass -File firmware\glove\press_test.ps1
#   powershell -ExecutionPolicy Bypass -File firmware\glove\press_test.ps1 -Port COM7
#
# Ctrl+C to stop. Close this before uploading a new sketch - Windows only lets
# one program hold a COM port at a time.

param([string]$Port = "COM10", [int]$Seconds = 60)

$p = New-Object System.IO.Ports.SerialPort($Port, 115200, 'None', 8, 'One')
$p.DtrEnable = $true
$p.ReadTimeout = 200
try { $p.Open() } catch { Write-Host "Could not open $Port : $_" -ForegroundColor Red; exit 1 }

Start-Sleep -Milliseconds 800
$p.DiscardInBuffer()
$p.Write("S`n")   # make sure streaming is on

$min = 1023; $max = 0; $buf = ""
Write-Host "Press the FSR. Ctrl+C to stop.`n" -ForegroundColor Cyan

$t0 = Get-Date
try {
  while (((Get-Date) - $t0).TotalSeconds -lt $Seconds) {
    try { $buf += $p.ReadExisting() } catch {}
    $parts = $buf -split "`n"
    $buf = $parts[-1]                      # keep the incomplete tail

    foreach ($line in $parts[0..($parts.Count - 2)]) {
      if (-not $line.StartsWith("G,")) { continue }
      $f = $line.Trim() -split ','
      if ($f.Count -lt 4) { continue }
      $adc = [int]$f[3]
      if ($adc -lt $min) { $min = $adc }
      if ($adc -gt $max) { $max = $adc }

      $mv  = [int]($adc * 3300 / 1023)
      # R_sensor = R_fixed * (Vsupply - Vout) / Vout
      $ohm = if ($mv -le 0) { "open" } elseif ($mv -ge 3300) { "0" } else { [int](10000 * (3300 - $mv) / $mv) }
      $bar = "#" * [int]($adc / 20)

      Write-Host ("`radc {0,4}  {1,5} mV  R {2,9}  span {3}-{4}  {5,-51}" -f `
                  $adc, $mv, $ohm, $min, $max, $bar) -NoNewline
    }
    Start-Sleep -Milliseconds 30
  }
} finally {
  $p.Close(); $p.Dispose()
  Write-Host "`n`nRecorded span: min=$min  max=$max  (usable range $($max - $min) of 1023)" -ForegroundColor Green
}
