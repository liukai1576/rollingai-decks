(*
keynote-to-html · extract.applescript  (v0.15)

Drives Keynote.app to walk a target document slide-by-slide and emit a
tab-separated record per iWork item — including elements inside groups
(recursively flattened with position offsets), and including items on the
slide's base layout (master) so template backgrounds carry through.

Changelog:
  v0.8  : (no AppleScript changes — font auto-shrink lives in build.py)
  v0.7  : Walk master / base-layout items per slide; emit BEFORE slide's
          own items so they render beneath (template backgrounds, footers).
  v0.6  : Extract opacity (0–100) per item.
  v0.5  : Accept --limit N as 2nd argv; stop after N non-skipped slides.
  v0.4  : Critical fix — rename local `rotation` variable to `rotDeg`
          (clashed with Keynote's reserved property name).
  v0.3  : Sentinel (-1) on fillR/G/B when fill type isn't color fill,
          distinguishing "no fill" from "true black fill".
  v0.2  : Recurses into 'group' items; emits flattened ITEM record per
          descendant with absolute position offsets. Extracts rotation,
          shape color fill, slide #SLIDE-META background color.

Format:
  Header:    "#TOTAL\t<slide_count>"
  Slide hdr: "#SLIDE\t<keynote_slide_no>\t<skipped:true|false>"
  Slide bg:  "#SLIDE-META\tbg_r\tbg_g\tbg_b"
  Element:
    "ITEM\t<type>\t<x>\t<y>\t<w>\t<h>\t<rotation>\t<file_name>\t<font>\t<font_size>\t<r>\t<g>\t<b>\t<fill_r>\t<fill_g>\t<fill_b>\t<corner_radius>\t<text_b64>"
       · type       ∈ {image, text, movie, shape, table, chart, group, other:*}
       · rotation   degrees (0–360)
       · fill_*     shape fill color (0 if none/unknown)
       · corner_radius  px (0 if not applicable)
       · text_b64   base64 of UTF-8 text
  Slide end: "#END-SLIDE"
  Done:      "#DONE"

Usage:
  osascript extract.applescript [<out.tsv> [<limit> [<doc-name>]]]
  · <out.tsv>     output path (default: stdout)
  · <limit>       0 = no limit; N = stop after N non-skipped slides
  · <doc-name>    Keynote doc name (e.g. "RollingAI分享 - 康师傅.key"); if
                  empty, falls back to front document. SHOULD be passed
                  when multiple Keynote docs are open — `front document`
                  is the whichever-the-user-clicked-last doc, not
                  necessarily ours.
*)

global gTargetDocName

on run argv
    set outPath to ""
    set nonSkippedLimit to 0  -- 0 = no limit
    set gTargetDocName to ""
    set targetSlidesArg to ""
    if (count of argv) > 0 then set outPath to item 1 of argv
    if (count of argv) > 1 then
        try
            set nonSkippedLimit to (item 2 of argv) as integer
        end try
    end if
    if (count of argv) > 2 then set gTargetDocName to item 3 of argv
    -- 4th arg: comma-separated 1-based slide numbers to extract (e.g. "74,83,86").
    -- Empty/missing = extract every non-skipped slide. When set, every slide
    -- NOT in the list is emitted as a "skipped" stub so build.py knows there's
    -- nothing to render for it (and the deck stays the same length).
    if (count of argv) > 3 then set targetSlidesArg to item 4 of argv

    -- Parse "74,83,86" into a list of integers.
    set targetSlides to {}
    if targetSlidesArg is not "" then
        set AppleScript's text item delimiters to ","
        set rawItems to text items of targetSlidesArg
        set AppleScript's text item delimiters to ""
        repeat with ri in rawItems
            try
                set end of targetSlides to ((ri as text) as integer)
            end try
        end repeat
    end if

    tell application id "com.apple.Keynote"
        if (count of documents) = 0 then
            error "No document open in Keynote. Open the .key file first."
        end if
        if gTargetDocName is "" then
            set theDoc to front document
            set gTargetDocName to name of theDoc
        else
            try
                set theDoc to (first document whose name is gTargetDocName)
            on error
                error "Document not found by name: " & gTargetDocName
            end try
        end if
        set slideCount to count of slides of theDoc
        -- Slide canvas size (Keynote exposes width/height on the document).
        -- Older / smaller .key files come in at 960×540 instead of 1920×1080;
        -- build.py reads this and scales coordinates so the renderer (which
        -- assumes 1920×1080) doesn't get a quarter-filled canvas.
        try
            set docW to width of theDoc
            set docH to height of theDoc
        on error
            set docW to 1920
            set docH to 1080
        end try
    end tell

    set headerOut to "#TOTAL" & tab & slideCount & linefeed
    set headerOut to headerOut & "#DOC-SIZE" & tab & docW & tab & docH & linefeed

    -- Incremental write: open the output file ONCE (truncate), write the
    -- header, then append each slide as soon as it's extracted. This way
    -- if the script is killed mid-run (timeout, user cancel, Keynote
    -- crash), the partial tsv is salvageable — build.py treats absent
    -- #DONE as fine. Previous behavior built the WHOLE tsv in memory and
    -- wrote it at the end, so any interruption wiped everything.
    if outPath is not "" then
        my writeToFile(headerOut, outPath)  -- truncates + writes
    end if
    set output to headerOut  -- keep growing for the in-memory return path

    set nonSkippedSeen to 0
    repeat with slideIdx from 1 to slideCount
        tell application id "com.apple.Keynote"
            try
                set isSkipped to skipped of slide slideIdx of (first document whose name is gTargetDocName)
            on error
                set isSkipped to false
            end try
        end tell
        if (count of targetSlides) > 0 and (targetSlides does not contain slideIdx) then
            set isSkipped to true
        end if
        if isSkipped then
            set slideRecord to "#SLIDE" & tab & slideIdx & tab & "true" & linefeed
        else
            set slideRecord to my extractSlide(slideIdx)
            set nonSkippedSeen to nonSkippedSeen + 1
        end if
        if outPath is not "" then
            my appendToFile(slideRecord, outPath)
        end if
        set output to output & slideRecord
        if (not isSkipped) and nonSkippedLimit > 0 and nonSkippedSeen >= nonSkippedLimit then
            exit repeat
        end if
    end repeat

    set output to output & "#DONE" & linefeed
    if outPath is not "" then
        my appendToFile("#DONE" & linefeed, outPath)
        return "OK: " & (length of output) & " chars written to " & outPath
    else
        return output
    end if
end run


on extractSlide(slideIdx)
    set out to ""

    tell application id "com.apple.Keynote"
        set theDoc to (first document whose name is gTargetDocName)
        set theSlide to slide slideIdx of theDoc
        set isSkipped to skipped of theSlide
        set skippedStr to "false"
        if isSkipped then set skippedStr to "true"
    end tell

    set out to out & "#SLIDE" & tab & slideIdx & tab & skippedStr & linefeed

    -- Slide background color (best effort)
    set bgR to 0
    set bgG to 0
    set bgB to 0
    tell application id "com.apple.Keynote"
        set theDoc to (first document whose name is gTargetDocName)
        set theSlide to slide slideIdx of theDoc
        try
            set bl to base layout of theSlide
            set bgFill to background fill type of bl
            -- if it's color fill, try to get the color
            if bgFill is color fill then
                try
                    set bgColor to background color of bl
                    set bgR to item 1 of bgColor
                    set bgG to item 2 of bgColor
                    set bgB to item 3 of bgColor
                end try
            end if
        end try
    end tell
    set out to out & "#SLIDE-META" & tab & bgR & tab & bgG & tab & bgB & linefeed

    -- Master layout items first (template backgrounds, branded chrome, etc).
    -- These render BENEATH the slide's own items, matching Keynote's draw order.
    tell application id "com.apple.Keynote"
        set theDoc to (first document whose name is gTargetDocName)
        set theSlide to slide slideIdx of theDoc
        try
            set bl to base layout of theSlide
            set masterItems to every iWork item of bl
        on error
            set masterItems to {}
        end try
        set itemList to every iWork item of theSlide
    end tell

    -- Master items are emitted with "MASTER" prefix; build.py uses this to
    -- decide whether to keep them (typically the slide-level bg covers them).
    repeat with mItm in masterItems
        set masterRec to my extractItemFlat(mItm, 0, 0)
        -- swap leading "ITEM" → "MASTER" for each line in the record (a single
        -- record can have multiple lines if it was a group)
        set out to out & my replaceLeading(masterRec, "ITEM", "MASTER")
    end repeat
    repeat with itm in itemList
        set out to out & my extractItemFlat(itm, 0, 0)
    end repeat

    set out to out & "#END-SLIDE" & linefeed
    return out
end extractSlide


-- Recursively extract an item; if it's a group, dive in and flatten with offset.
on extractItemFlat(itm, offsetX, offsetY)
    set out to ""

    set elemType to "other"
    tell application id "com.apple.Keynote"
        try
            set cls to (class of itm) as string
            if cls is "image" then
                set elemType to "image"
            else if cls is "text item" then
                set elemType to "text"
            else if cls is "movie" then
                set elemType to "movie"
            else if cls is "shape" then
                set elemType to "shape"
            else if cls is "table" then
                set elemType to "table"
            else if cls is "chart" then
                set elemType to "chart"
            else if cls is "group" then
                set elemType to "group"
            else
                set elemType to "other:" & cls
            end if
        end try
    end tell

    -- get position + size (may fail for some items)
    set px to 0
    set py to 0
    set pw to 0
    set ph to 0
    tell application id "com.apple.Keynote"
        try
            set pos to position of itm
            set px to (item 1 of pos) + offsetX
            set py to (item 2 of pos) + offsetY
        end try
        try
            set pw to width of itm
            set ph to height of itm
        end try
    end tell

    -- If this is a group, recurse into children. IMPORTANT: Keynote 14.5
    -- AppleScript returns child positions as ABSOLUTE slide coordinates
    -- (NOT relative to the group's top-left, contrary to early v0.2
    -- assumption). So we recurse with (0, 0) offset — passing the group's
    -- position would double-count and push elements off the canvas.
    -- Verified empirically on slide 60: group at (119, 542), child reports
    -- (179, 542) which IS the absolute slide position, not relative (60, 0).
    if elemType is "group" then
        -- Emit a debug record for the group itself (build.py can skip these)
        set out to out & "ITEM" & tab & "group" & tab & px & tab & py & tab & pw & tab & ph & tab & "0" & tab & "" & tab & "" & tab & "0" & tab & "0" & tab & "0" & tab & "0" & tab & "0" & tab & "0" & tab & "0" & tab & "0" & tab & "100" & tab & "" & linefeed
        tell application id "com.apple.Keynote"
            try
                set children to every iWork item of itm
            on error
                set children to {}
            end try
        end tell
        repeat with child in children
            set out to out & my extractItemFlat(child, 0, 0)
        end repeat
        return out
    end if

    -- Normal element — gather attributes
    set rotDeg to 0
    set fname to ""
    set theText to ""
    set fontName to ""
    set fontSize to 0
    set r to 0
    set g to 0
    set b to 0
    set fillR to -1  -- sentinel: -1 = no extractable color fill; ≥ 0 = real RGB value
    set fillG to -1
    set fillB to -1
    set cornerR to 0
    set opacityPct to 100  -- 0–100 (Keynote convention)

    tell application id "com.apple.Keynote"
        try
            set rotDeg to (rotation of itm) as real
        end try
        try
            set opacityPct to (opacity of itm) as real
        end try

        if elemType is "image" or elemType is "movie" then
            try
                set fname to file name of itm
            end try
        end if

        if elemType is "text" or elemType is "shape" then
            try
                set theText to object text of itm
            end try
            try
                set fontSize to size of object text of itm
            end try
            try
                set fontName to font of object text of itm
            end try
            try
                set colorList to color of object text of itm
                set r to item 1 of colorList
                set g to item 2 of colorList
                set b to item 3 of colorList
            end try
        end if

        if elemType is "shape" then
            try
                set ft to background fill type of itm
                if ft is color fill then
                    try
                        set fillColor to background color of itm
                        set fillR to item 1 of fillColor
                        set fillG to item 2 of fillColor
                        set fillB to item 3 of fillColor
                    end try
                end if
            end try
            -- Note: AppleScript has no direct 'corner radius' property exposed by Keynote.
            -- We leave cornerR at 0 — build.py applies a default for visually-rounded shapes.
        end if
    end tell

    set textB64 to my base64Encode(theText)

    set rec to "ITEM" & tab & elemType & tab & px & tab & py & tab & pw & tab & ph & tab & rotDeg & tab & fname & tab & fontName & tab & fontSize & tab & r & tab & g & tab & b & tab & fillR & tab & fillG & tab & fillB & tab & cornerR & tab & opacityPct & tab & textB64 & linefeed

    -- For text/shape elements with NON-UNIFORM styling, also emit per-run
    -- RUN records (one per detected style segment). Keynote stores each
    -- run-of-styled-characters separately; we walk char-by-char and emit a
    -- new RUN every time font, size, or color changes. build.py uses RUNs
    -- to emit <span>-styled HTML when present, falling back to the single
    -- ITEM style otherwise.
    if (elemType is "text" or elemType is "shape") and theText is not "" then
        set rec to rec & my extractTextRuns(itm)
    end if

    -- For TABLE elements, emit one CELL line per cell so build.py can
    -- reconstruct an HTML <table>.
    if elemType is "table" then
        set rec to rec & my extractTableCells(itm)
    end if

    -- For CHART elements, emit SERIES + POINT records so build.py can
    -- reconstruct an SVG/HTML chart.
    if elemType is "chart" then
        set rec to rec & my extractChartData(itm)
    end if

    return rec
end extractItemFlat


-- Walk a chart iWork item, emit chart metadata + per-series data points.
-- Format:
--   CHART_META\ttype\tnRows\tnCols
--   CATEGORY\tlabel_b64                  (one per category, in row order)
--   SERIES\tname_b64                     (one per series)
--   POINT\tseries_idx\tcategory_idx\tvalue
-- Robust to errors — chart introspection is the least-stable AppleScript
-- API surface. Always returns a string, never raises.
on extractChartData(itm)
    set out to ""
    tell application id "com.apple.Keynote"
        try
            -- Keynote charts have `chart type` (column, bar, line, pie...)
            -- and a chart_data property. Different versions expose
            -- different selectors; try several.
            set chartType to ""
            try
                set chartType to (chart type of itm) as text
            end try
            set out to out & "CHART_META" & tab & chartType & linefeed
        on error
            return ""
        end try
        -- Try `chart data of itm` → can be a 2D list or a list of records.
        -- Keynote 14+ exposes `chart data` as a list of lists: header row +
        -- value rows. First column = category labels; first row = series
        -- names. Below code handles that pattern best-effort.
        try
            set cd to chart data of itm
            -- cd is a list of rows; row 1 is series headers (with empty
            -- first cell). Row 2..N are categories with values.
            set nRows to count of cd
            if nRows < 2 then return out
            set hdrRow to item 1 of cd
            set nCols to count of hdrRow
            -- Series names: hdrRow[2..nCols]
            repeat with cI from 2 to nCols
                set sName to ""
                try
                    set sName to (item cI of hdrRow) as text
                end try
                set out to out & "SERIES" & tab & my base64Encode(sName) & linefeed
            end repeat
            -- Categories + points
            repeat with rI from 2 to nRows
                set rowList to item rI of cd
                set catLabel to ""
                try
                    set catLabel to (item 1 of rowList) as text
                end try
                set out to out & "CATEGORY" & tab & my base64Encode(catLabel) & linefeed
                repeat with cI from 2 to nCols
                    set v to 0
                    try
                        set v to (item cI of rowList) as real
                    end try
                    -- series_idx 0-based: cI-2
                    -- category_idx 0-based: rI-2
                    set out to out & "POINT" & tab & (cI - 2) & tab & (rI - 2) & tab & v & linefeed
                end repeat
            end repeat
        end try
    end tell
    return out
end extractChartData


-- Walk a table iWork item and emit one CELL row per (row, col).
-- Robust to errors (some Keynote builds throw on tables created via
-- the Numbers UI). Always returns a string, never raises.
on extractTableCells(itm)
    set out to ""
    tell application id "com.apple.Keynote"
        try
            set rowCount to row count of itm
            set colCount to column count of itm
        on error
            return ""
        end try
        set colWidths to {}
        set rowHeights to {}
        repeat with cI from 1 to colCount
            try
                set end of colWidths to (width of column cI of itm) as real
            on error
                set end of colWidths to 0.0
            end try
        end repeat
        repeat with rI from 1 to rowCount
            try
                set end of rowHeights to (height of row rI of itm) as real
            on error
                set end of rowHeights to 0.0
            end try
        end repeat
        repeat with rI from 1 to rowCount
            repeat with cI from 1 to colCount
                set cellText to ""
                set cellFont to ""
                set cellSize to 0
                set cellR to 0
                set cellG to 0
                set cellB to 0
                set cellFillR to -1
                set cellFillG to -1
                set cellFillB to -1
                try
                    set theCell to cell cI of row rI of itm
                    try
                        set cellText to (formatted value of theCell) as text
                    on error
                        try
                            set cellText to (value of theCell) as text
                        end try
                    end try
                    -- Cell text font / size. Keynote AppleScript exposes
                    -- text-style properties on `cell` directly (uniform
                    -- styling per cell; per-character isn't reachable
                    -- without diving into IWA).
                    try
                        set cellFont to font name of theCell as text
                    end try
                    try
                        set cellSize to size of theCell as real
                    end try
                    try
                        set cTC to text color of theCell
                        set cellR to item 1 of cTC
                        set cellG to item 2 of cTC
                        set cellB to item 3 of cTC
                    end try
                    -- Cell fill. Older Keynote versions don't expose this;
                    -- the try/on-error keeps us silent on those.
                    try
                        set cFC to background color of theCell
                        set cellFillR to item 1 of cFC
                        set cellFillG to item 2 of cFC
                        set cellFillB to item 3 of cFC
                    end try
                end try
                set cw to item cI of colWidths
                set rh to item rI of rowHeights
                set cellB64 to my base64Encode(cellText)
                -- CELL\trow\tcol\tcw\trh\tfont\tsize\tr\tg\tb\tfill_r\tfill_g\tfill_b\ttext_b64
                set out to out & "CELL" & tab & rI & tab & cI & tab & cw & tab & rh & tab & cellFont & tab & cellSize & tab & cellR & tab & cellG & tab & cellB & tab & cellFillR & tab & cellFillG & tab & cellFillB & tab & cellB64 & linefeed
            end repeat
        end repeat
    end tell
    return out
end extractTableCells


-- Detect multi-run text within a single Keynote text/shape item.
-- Returns 0 or more "RUN ...\n" lines. Empty string if uniform style.
on extractTextRuns(itm)
    set out to ""
    tell application id "com.apple.Keynote"
        tell itm
            try
                set nChars to count of characters of object text
                if nChars < 2 then return ""
                -- Cheap check: compare first vs last char. If same font+size,
                -- assume uniform (skip the slow per-char scan).
                set f1 to font of character 1 of object text
                set s1 to size of character 1 of object text
                set fL to font of character nChars of object text
                set sL to size of character nChars of object text
                if f1 = fL and s1 = sL then return ""
            on error
                return ""
            end try

            -- Multi-run: walk chars, accumulate run boundaries
            set runStart to 1
            set runFont to f1
            set runSize to s1
            set runColor to {0, 0, 0}
            try
                set runColor to color of character 1 of object text
            end try
            repeat with i from 2 to nChars
                set thisFont to runFont
                set thisSize to runSize
                set thisColor to runColor
                try
                    set thisFont to font of character i of object text
                end try
                try
                    set thisSize to size of character i of object text
                end try
                try
                    set thisColor to color of character i of object text
                end try
                if thisFont ≠ runFont or thisSize ≠ runSize or (thisColor as string) ≠ (runColor as string) then
                    -- emit run [runStart, i-1]
                    set runText to ""
                    try
                        set runText to (text runStart thru (i - 1) of (object text as string))
                    end try
                    set tB64 to my base64Encode(runText)
                    set out to out & "RUN" & tab & runFont & tab & runSize & tab & (item 1 of runColor) & tab & (item 2 of runColor) & tab & (item 3 of runColor) & tab & tB64 & linefeed
                    set runStart to i
                    set runFont to thisFont
                    set runSize to thisSize
                    set runColor to thisColor
                end if
            end repeat
            -- emit final run
            set runText to ""
            try
                set runText to (text runStart thru nChars of (object text as string))
            end try
            set tB64 to my base64Encode(runText)
            set out to out & "RUN" & tab & runFont & tab & runSize & tab & (item 1 of runColor) & tab & (item 2 of runColor) & tab & (item 3 of runColor) & tab & tB64 & linefeed
        end tell
    end tell
    return out
end extractTextRuns


on base64Encode(s)
    if s is "" or s is missing value then return ""
    try
        set encoded to do shell script "printf '%s' " & (quoted form of (s as string)) & " | base64 | tr -d '\\n'"
        return encoded
    on error
        return ""
    end try
end base64Encode


on replaceLeading(s, oldHead, newHead)
    -- Replace "<oldHead>\t" with "<newHead>\t" at the start of every line in s.
    -- Uses text item delimiters with linefeed; avoids the reserved word `lines`.
    set astid to AppleScript's text item delimiters
    set linePrefix to oldHead & tab
    set newPrefix to newHead & tab
    set AppleScript's text item delimiters to linefeed
    set rawParts to text items of s
    set AppleScript's text item delimiters to astid
    set rebuilt to ""
    set n to count of rawParts
    repeat with i from 1 to n
        set ln to item i of rawParts
        set lnLen to count of ln
        set prefLen to count of linePrefix
        if lnLen ≥ prefLen and (text 1 thru prefLen of ln) is linePrefix then
            if lnLen > prefLen then
                set rebuilt to rebuilt & newPrefix & (text (prefLen + 1) thru lnLen of ln)
            else
                set rebuilt to rebuilt & newPrefix
            end if
        else
            set rebuilt to rebuilt & ln
        end if
        if i < n then set rebuilt to rebuilt & linefeed
    end repeat
    return rebuilt
end replaceLeading


on writeToFile(content, posixPath)
    set fileRef to open for access (POSIX file posixPath) with write permission
    try
        set eof of fileRef to 0
        write content to fileRef as «class utf8»
    end try
    close access fileRef
end writeToFile

-- Append-mode write. Used for incremental slide-by-slide output so
-- partial extracts survive an interrupted run. Opens, seeks to EOF,
-- writes, closes — same pattern as writeToFile but without the truncate.
on appendToFile(content, posixPath)
    set fileRef to open for access (POSIX file posixPath) with write permission
    try
        write content to fileRef starting at eof as «class utf8»
    end try
    close access fileRef
end appendToFile
