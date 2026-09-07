[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourcePptx,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$ExpectedFont = '',
    [switch]$RequireNotes,
    [switch]$Force,
    [switch]$KeepStaging
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

if (-not (Test-Path -LiteralPath $SourcePptx -PathType Leaf)) {
    throw "Source PPTX does not exist: $SourcePptx"
}

$helper = 'C:\Users\AdminLF\.codex\scripts\office_ascii_stage.ps1'
if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    throw "Office staging helper does not exist: $helper"
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDir).TrimEnd('\')
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null
$deliveryRenderDir = Join-Path $resolvedOutput 'rendered_slides'
$deliveryAudit = Join-Path $resolvedOutput 'wps_audit.json'

foreach ($target in @($deliveryRenderDir, $deliveryAudit)) {
    if (Test-Path -LiteralPath $target) {
        if (-not $Force) {
            throw "Output already exists; pass -Force to replace it: $target"
        }
        $resolvedTarget = (Resolve-Path -LiteralPath $target).Path
        if (-not $resolvedTarget.StartsWith($resolvedOutput + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe output target: $resolvedTarget"
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

$taskId = 'wpsaudit_' + [Guid]::NewGuid().ToString('N')
$taskDir = & $helper -Action Create -TaskId $taskId
$stagedPptx = & $helper -Action StageIn -TaskId $taskId -Source $SourcePptx -Name 'input.pptx'
$stagedRender = Join-Path $taskDir 'render'
$stagedAudit = Join-Path $taskDir 'wps_audit.json'
New-Item -ItemType Directory -Path $stagedRender -Force | Out-Null

function Get-ShapeTextRecords {
    param([Parameter(Mandatory = $true)]$Shape)

    try {
        if ([int]$Shape.Type -eq 6) {
            for ($index = 1; $index -le $Shape.GroupItems.Count; $index++) {
                Get-ShapeTextRecords -Shape $Shape.GroupItems.Item($index)
            }
        }
    } catch {}

    try {
        if ($Shape.HasTextFrame -and $Shape.TextFrame.HasText) {
            $fontName = [string]$Shape.TextFrame.TextRange.Font.Name
            $fontFarEast = ''
            try {
                $fontFarEast = [string]$Shape.TextFrame.TextRange.Font.NameFarEast
            } catch {}
            $fontSize = [double]$Shape.TextFrame.TextRange.Font.Size
            [ordered]@{
                font_name = $fontName
                font_far_east = $fontFarEast
                font_size = $fontSize
            }
        }
    } catch {}
}

$app = $null
$presentation = $null
try {
    $app = New-Object -ComObject KWPP.Application
    try { $app.Visible = $false } catch {}
    $presentation = $app.Presentations.Open($stagedPptx, $true, $true, $false)

    $slides = @()
    $notesNonempty = 0
    $expectedFontSlides = 0
    foreach ($slide in $presentation.Slides) {
        $textRecords = @()
        foreach ($shape in $slide.Shapes) {
            $textRecords += @(Get-ShapeTextRecords -Shape $shape)
        }
        $fontNames = @(
            $textRecords |
                ForEach-Object { @($_.font_name, $_.font_far_east) } |
                Where-Object { $_ } |
                Sort-Object -Unique
        )
        $fontSizes = @(
            $textRecords |
                ForEach-Object { [double]$_.font_size } |
                Where-Object { $_ -gt 0 }
        )
        if ($ExpectedFont -and $fontNames -contains $ExpectedFont) {
            $expectedFontSlides++
        }

        $notesText = ''
        try {
            foreach ($noteShape in $slide.NotesPage.Shapes) {
                try {
                    if ($noteShape.HasTextFrame -and $noteShape.TextFrame.HasText) {
                        $notesText += [string]$noteShape.TextFrame.TextRange.Text
                        $notesText += "`n"
                    }
                } catch {}
            }
        } catch {}
        if ($notesText.Trim().Length -gt 0) {
            $notesNonempty++
        }

        $minFontSize = 0
        if ($fontSizes.Count) {
            $minFontSize = [math]::Round(
                (($fontSizes | Measure-Object -Minimum).Minimum),
                2
            )
        }
        $slides += [ordered]@{
            slide = [int]$slide.SlideIndex
            text_shape_count = $textRecords.Count
            fonts = $fontNames
            min_font_size = $minFontSize
            notes_characters = $notesText.Length
        }
    }

    $presentation.Export($stagedRender, 'PNG', 1920, 1080)
    $renderedFiles = @(
        Get-ChildItem -LiteralPath $stagedRender -Filter '*.PNG' -File
    )
    $pngCount = $renderedFiles.Count
    $passed = $pngCount -eq $slides.Count
    if ($ExpectedFont) {
        $passed = $passed -and ($expectedFontSlides -eq $slides.Count)
    }
    if ($RequireNotes) {
        $passed = $passed -and ($notesNonempty -eq $slides.Count)
    }

    $result = [ordered]@{
        schema = 'assemble-podcast-ppt-video.wps-render-audit.v1'
        application = 'KWPP.Application'
        source_pptx = [System.IO.Path]::GetFullPath($SourcePptx)
        expected_font = $ExpectedFont
        require_notes = [bool]$RequireNotes
        passed = $passed
        slides = $slides.Count
        rendered_pngs = $pngCount
        notes_nonempty_slides = $notesNonempty
        slides_reporting_expected_font = $expectedFontSlides
        slide_details = $slides
    }
    [System.IO.File]::WriteAllText(
        $stagedAudit,
        ($result | ConvertTo-Json -Depth 8),
        $utf8
    )

    New-Item -ItemType Directory -Path $deliveryRenderDir -Force | Out-Null
    foreach ($file in $renderedFiles) {
        Copy-Item -LiteralPath $file.FullName -Destination $deliveryRenderDir -Force
    }
    Copy-Item -LiteralPath $stagedAudit -Destination $deliveryAudit -Force

    Write-Output "slides=$($slides.Count); rendered=$pngCount; notes_nonempty=$notesNonempty; expected_font_slides=$expectedFontSlides; audit=$deliveryAudit; render=$deliveryRenderDir"
    if (-not $passed) {
        throw 'WPS render audit failed its requested acceptance checks.'
    }
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) | Out-Null
    }
    if ($null -ne $app) {
        try { $app.Quit() } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    if (-not $KeepStaging) {
        try { & $helper -Action Clean -TaskId $taskId | Out-Null } catch {}
    }
}
