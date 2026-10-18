# Neon Uploader native Windows 11 file browser for the Raspberry Pi share.
# Requires only Windows PowerShell 5.1 / .NET Framework WinForms, no Python.
# Credentials are saved per-user by neon-client.ps1 (Export-Clixml / DPAPI).
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$settings = Join-Path $env:APPDATA 'NeonUploader'
$urlFile = Join-Path $settings 'pi-url.txt'
$credentialFile = Join-Path $settings 'credential.xml'
if (!(Test-Path -LiteralPath $urlFile) -or !(Test-Path -LiteralPath $credentialFile)) {
    throw 'Windows client is not configured. Run neon-client.bat -Setup first.'
}
$script:BaseUrl = (Get-Content -LiteralPath $urlFile -Raw).TrimEnd("/", "`r", "`n", ' ')
$uri = $null
if (![Uri]::TryCreate($script:BaseUrl, [UriKind]::Absolute, [ref]$uri) -or
    $uri.Scheme -notin @('http', 'https') -or $uri.UserInfo -or $uri.AbsolutePath -ne '/') {
    throw 'Saved Pi address is invalid. Run neon-client.bat -Setup to configure it.'
}
$credential = Import-Clixml -LiteralPath $credentialFile
if ($credential -isnot [System.Management.Automation.PSCredential] -or $credential.UserName -ne 'neon') {
    throw 'Windows credential is invalid. Run neon-client.bat -Setup.'
}
$plain = $credential.GetNetworkCredential().Password
$script:Headers = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('neon:' + $plain)) }
$plain = $null
$credential = $null

function Invoke-NeonGet([string]$relative) {
    $uri = $script:BaseUrl + '/api/files?path=' + [Uri]::EscapeDataString($relative)
    return Invoke-RestMethod -Method Get -Uri $uri -Headers $script:Headers -TimeoutSec 25
}
function Invoke-NeonJson([string]$endpoint, $data) {
    $body = ConvertTo-Json -InputObject $data -Compress -Depth 8
    return Invoke-RestMethod -Method Post -Uri ($script:BaseUrl + $endpoint) -Headers $script:Headers `
        -ContentType 'application/json' -Body $body -TimeoutSec 120
}
function Show-Error([string]$message) {
    [void][System.Windows.Forms.MessageBox]::Show($script:Window, $message, 'Neon Uploader',
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
}
function New-Button([string]$caption, [int]$width) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $caption; $button.Width = $width; $button.Height = 30
    $button.Margin = [System.Windows.Forms.Padding]::new(3,3,3,3)
    return $button
}

$script:Window = New-Object System.Windows.Forms.Form
$script:Window.Text = 'Neon Uploader | Pi Share Explorer'
$script:Window.Width = 1130
$script:Window.Height = 740
$script:Window.MinimumSize = [System.Drawing.Size]::new(790,490)
$script:Window.StartPosition = 'CenterScreen'
$script:Window.Font = [System.Drawing.Font]::new('Segoe UI', 9)

$outer = New-Object System.Windows.Forms.TableLayoutPanel
$outer.Dock = 'Fill'
$outer.RowCount = 4; $outer.ColumnCount = 1
[void]$outer.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute, 44)))
[void]$outer.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute, 44)))
[void]$outer.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent, 100)))
[void]$outer.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute, 48)))
$script:Window.Controls.Add($outer)

$navigation = New-Object System.Windows.Forms.FlowLayoutPanel
$navigation.Dock = 'Fill'; $navigation.WrapContents = $false
$navigation.AutoScroll = $true
[void]$outer.Controls.Add($navigation,0,0)
$backButton = New-Button 'Back' 64; $upButton = New-Button 'Up' 52
$homeButton = New-Button 'Share' 65; $refreshButton = New-Button 'Refresh' 77
foreach ($b in @($backButton,$upButton,$homeButton,$refreshButton)) { [void]$navigation.Controls.Add($b) }
$pathBox = New-Object System.Windows.Forms.TextBox
$pathBox.Width=520; $pathBox.Margin=[System.Windows.Forms.Padding]::new(7,7,2,2)
$pathBox.Anchor='Left,Right'; [void]$navigation.Controls.Add($pathBox)
$goButton = New-Button 'Go' 48; [void]$navigation.Controls.Add($goButton)

$actions = New-Object System.Windows.Forms.FlowLayoutPanel
$actions.Dock='Fill'; $actions.WrapContents=$false; $actions.AutoScroll=$true
[void]$outer.Controls.Add($actions,0,1)
$downloadButton=New-Button 'Download' 98
$zipButton=New-Button 'Download ZIP' 112
$selectButton=New-Button 'Select All' 90
$clearButton=New-Button 'Clear' 60
$newFolderButton=New-Button 'New Folder' 100
$renameButton=New-Button 'Rename' 77
$deleteButton=New-Button 'Delete' 74
$webButton=New-Button 'Open in Opera GX' 140
foreach ($b in @($downloadButton,$zipButton,$selectButton,$clearButton,$newFolderButton,$renameButton,$deleteButton,$webButton)) {
    [void]$actions.Controls.Add($b)
}

$split = New-Object System.Windows.Forms.SplitContainer
$split.Dock = 'Fill' # Set splitter distance after the form has a real layout size.
[void]$outer.Controls.Add($split,0,2)
$script:Tree=New-Object System.Windows.Forms.TreeView
$script:Tree.Dock = 'Fill'; $script:Tree.HideSelection=$false
$split.Panel1.Controls.Add($script:Tree)
$right = New-Object System.Windows.Forms.TableLayoutPanel
$right.Dock='Fill'; $right.RowCount=2; $right.ColumnCount=1
[void]$right.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute, 42)))
[void]$right.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent, 100)))
$split.Panel2.Controls.Add($right)
$filterRow=New-Object System.Windows.Forms.FlowLayoutPanel
$filterRow.Dock='Fill'
$searchLabel=New-Object System.Windows.Forms.Label
$searchLabel.Text='Find in folder:'; $searchLabel.AutoSize=$true
$searchLabel.Margin=[System.Windows.Forms.Padding]::new(6,12,4,4)
$script:Search=New-Object System.Windows.Forms.TextBox
$script:Search.Width=280; $script:Search.Margin=[System.Windows.Forms.Padding]::new(4,8,4,4)
[void]$filterRow.Controls.Add($searchLabel); [void]$filterRow.Controls.Add($script:Search)
[void]$right.Controls.Add($filterRow,0,0)
$script:Files = New-Object System.Windows.Forms.ListView
$script:Files.Dock='Fill'; $script:Files.View='Details'; $script:Files.FullRowSelect=$true
$script:Files.HideSelection=$false; $script:Files.MultiSelect=$true
$script:Files.CheckBoxes=$true; $script:Files.GridLines=$false
[void]$script:Files.Columns.Add('Name',310)
[void]$script:Files.Columns.Add('Type',95)
[void]$script:Files.Columns.Add('Size',105)
[void]$script:Files.Columns.Add('Modified',160)
[void]$right.Controls.Add($script:Files,0,1)

$statusArea = New-Object System.Windows.Forms.TableLayoutPanel
$statusArea.Dock='Fill'; $statusArea.RowCount=2; $statusArea.ColumnCount=1
[void]$statusArea.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Absolute, 22)))
[void]$statusArea.RowStyles.Add(([System.Windows.Forms.RowStyle]::new([System.Windows.Forms.SizeType]::Percent, 100)))
$script:ShareLabel=New-Object System.Windows.Forms.Label
$script:ShareLabel.Dock='Fill'; $script:ShareLabel.AutoEllipsis=$true
$script:Status=New-Object System.Windows.Forms.Label
$script:Status.Dock='Fill'; $script:Status.AutoEllipsis=$true
$script:ShareLabel.Text='Connecting to Pi...'; $script:Status.Text=''
[void]$statusArea.Controls.Add($script:ShareLabel,0,0)
[void]$statusArea.Controls.Add($script:Status,0,1)
[void]$outer.Controls.Add($statusArea,0,3)

$script:Path=''
$script:Items=@()
$script:History=New-Object 'System.Collections.Generic.List[string]'
$script:HistoryIndex=-1
$script:SortColumn=0; $script:SortDescending=$false
$script:SharePath=''

function Format-Size($n) {
    if ($null -eq $n) { return '' }
    [double]$number=$n
    foreach ($unit in @('B','KB','MB','GB','TB')) {
        if ($number -lt 1024 -or $unit -eq 'TB') { return ('{0:N1} {1}' -f $number,$unit) }
        $number = $number/1024
    }
}
function Valid-RelativePath([string]$relative) {
    $relative=$relative.Trim().Replace('\','/').Trim('/')
    if ($relative -match '(^|/)\.\.(/|$)' -or $relative -match '(^|/)\.(/|$)' -or
        $relative -match '^[A-Za-z]:' -or $relative.Contains([char]0) -or $relative.StartsWith('//')) {
        throw 'Enter a share-relative folder, not a path outside the configured Pi share.'
    }
    return $relative
}
function Visible-Items {
    $filter=$script:Search.Text.Trim()
    $items=@($script:Items | Where-Object { !$filter -or $_.name.IndexOf($filter, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
    if ($script:SortColumn -eq 2) { $property = 'size' }
    elseif ($script:SortColumn -eq 3) { $property = 'modified' }
    else { $property = 'name' }
    $items = @($items | Sort-Object -Property @(
        @{Expression={ if($_.type -eq 'directory'){0}else{1} };Descending=$false},
        @{Expression={ $_.$property };Descending=$script:SortDescending}
    ))
    return $items
}
function Draw-Items {
    $script:Files.BeginUpdate()
    try {
        $script:Files.Items.Clear()
        foreach ($item in (Visible-Items)) {
            $name = if($item.type -eq 'directory'){'[DIR] ' + $item.name}else{$item.name}
            $row = [System.Windows.Forms.ListViewItem]::new($name)
            $row.Tag=$item
            [void]$row.SubItems.Add($(if ($item.type -eq 'directory') {'Folder'}else{'File'}))
            [void]$row.SubItems.Add((Format-Size $item.size))
            $date=''
            if ($item.modified) {
                try { $date=([DateTimeOffset]::Parse([string]$item.modified)).ToLocalTime().ToString('yyyy-MM-dd HH:mm') } catch { $date=[string]$item.modified }
            }
            [void]$row.SubItems.Add($date)
            [void]$script:Files.Items.Add($row)
        }
    } finally { $script:Files.EndUpdate() }
    $script:Status.Text=('{0} item(s) shown | {1} total | Folder: /{2}' -f $script:Files.Items.Count,$script:Items.Count,$script:Path)
}
function Get-SelectedItems {
    $rows = if($script:Files.CheckedItems.Count -gt 0) {$script:Files.CheckedItems} else {$script:Files.SelectedItems}
    return @($rows | ForEach-Object { $_.Tag })
}
function Create-TreeNode([string]$title, [string]$relative, [bool]$withPlaceholder) {
    $node=[System.Windows.Forms.TreeNode]::new($title)
    $node.Tag=$relative
    if($withPlaceholder) { [void]$node.Nodes.Add('Loading...') }
    return $node
}
function Populate-TreeNode($node) {
    if ($node.Nodes.Count -ne 1 -or $node.Nodes[0].Text -ne 'Loading...') { return }
    $data = Invoke-NeonGet ([string]$node.Tag)
    $node.Nodes.Clear()
    foreach ($folder in @($data.items | Where-Object {$_.type -eq 'directory'})) {
        [void]$node.Nodes.Add((Create-TreeNode ([string]$folder.name) ([string]$folder.path) $true))
    }
}
function Navigate-To([string]$destination, [bool]$fromHistory=$false) {
    $destination=Valid-RelativePath $destination
    $data=Invoke-NeonGet $destination
    if (!$data.PSObject.Properties['share_root'] -or !$data.share_root) {
        throw 'The Pi is running an old server without share metadata. Update the Pi with git pull, stop the old process, and restart Neon Uploader.'
    }
    $script:SharePath=[string]$data.share_root
    $script:Path=[string]$data.path
    $script:Items=@($data.items)
    $script:ShareLabel.Text='Pi: '+$script:BaseUrl+' | Root: '+$script:SharePath+' | Server v'+[string]$data.version
    $script:ShareLabel.ForeColor=[System.Drawing.Color]::DarkSlateBlue
    $pathBox.Text=$script:Path
    $script:Search.Text=''
    Draw-Items
    if (!$fromHistory) {
        while ($script:History.Count -gt ($script:HistoryIndex + 1)) { $script:History.RemoveAt($script:History.Count-1) }
        $script:History.Add($script:Path)
        $script:HistoryIndex=$script:History.Count-1
    }
    $backButton.Enabled=$script:HistoryIndex -gt 0
    $upButton.Enabled=$script:Path -ne ''
}
function Refresh-Current { Navigate-To $script:Path $true }
function Parent-Path([string]$relative) {
    $pos=$relative.LastIndexOf('/')
    if ($pos -lt 0) { return '' }
    return $relative.Substring(0,$pos)
}
function Download-One($item) {
    if($null -eq $item) { throw 'Select a file first.' }
    if ($item.type -eq 'directory') { Download-Zip @($item); return }
    $dlg = New-Object System.Windows.Forms.SaveFileDialog
    $dlg.FileName=[string]$item.name
    $dlg.Title='Download file from Raspberry Pi'
    if($dlg.ShowDialog($script:Window) -ne [System.Windows.Forms.DialogResult]::OK) { return }
    $url=$script:BaseUrl+'/api/download?path='+[Uri]::EscapeDataString([string]$item.path)
    Invoke-WebRequest -Method Get -Uri $url -Headers $script:Headers -OutFile $dlg.FileName -TimeoutSec 600 -UseBasicParsing | Out-Null
    $script:Status.Text='Downloaded: '+$dlg.FileName
}
function Download-Zip($selected) {
    $list=@($selected)
    if($list.Count -eq 0) { throw 'Check or select at least one file/folder.' }
    $dlg=New-Object System.Windows.Forms.SaveFileDialog
    $dlg.FileName='neon-selection.zip'
    $dlg.Filter='ZIP archives (*.zip)|*.zip|All files (*.*)|*.*'
    if($dlg.ShowDialog($script:Window) -ne [System.Windows.Forms.DialogResult]::OK) { return }
    $names=@($list | ForEach-Object { [string]$_.path })
    $body=ConvertTo-Json -InputObject @{ paths=$names } -Compress -Depth 8
    Invoke-WebRequest -Method Post -Uri ($script:BaseUrl+'/api/download-zip') -Headers $script:Headers `
        -ContentType 'application/json' -Body $body -OutFile $dlg.FileName -TimeoutSec 600 -UseBasicParsing | Out-Null
    $script:Status.Text='Downloaded ZIP: '+$dlg.FileName
}
function Download-CurrentSelection {
    $list=@(Get-SelectedItems)
    if($list.Count -eq 1) { Download-One $list[0] }
    elseif($list.Count -gt 1) { Download-Zip $list }
    else { throw 'Check/select files first. Double-click folders to browse.' }
}
function New-Folder {
    $dialog=New-Object System.Windows.Forms.Form
    $dialog.Text='Create a folder'; $dialog.Size=[System.Drawing.Size]::new(390,155)
    $dialog.StartPosition='CenterParent'; $dialog.FormBorderStyle='FixedDialog'
    $input=New-Object System.Windows.Forms.TextBox
    $input.Location=[System.Drawing.Point]::new(16,18); $input.Width=340
    $button=New-Button 'Create' 94; $button.Location=[System.Drawing.Point]::new(264,56)
    [void]$dialog.Controls.Add($input); [void]$dialog.Controls.Add($button)
    $button.Add_Click({ $dialog.DialogResult=[System.Windows.Forms.DialogResult]::OK; $dialog.Close() })
    if($dialog.ShowDialog($script:Window) -ne [System.Windows.Forms.DialogResult]::OK) { return }
    if(!$input.Text.Trim()) { return }
    [void](Invoke-NeonJson '/api/folders' @{path=$script:Path;name=$input.Text.Trim()})
    Refresh-Current
}
function Rename-Selected {
    $selected=@(Get-SelectedItems)
    if($selected.Count -ne 1) { throw 'Select exactly one item to rename.' }
    $item=$selected[0]
    $dialog=New-Object System.Windows.Forms.Form
    $dialog.Text='Rename item'; $dialog.Size=[System.Drawing.Size]::new(400,155)
    $dialog.StartPosition='CenterParent'; $dialog.FormBorderStyle='FixedDialog'
    $input=New-Object System.Windows.Forms.TextBox
    $input.Location=[System.Drawing.Point]::new(16,18); $input.Width=350; $input.Text=[string]$item.name
    $button=New-Button 'Rename' 94; $button.Location=[System.Drawing.Point]::new(270,56)
    [void]$dialog.Controls.Add($input); [void]$dialog.Controls.Add($button)
    $button.Add_Click({ $dialog.DialogResult=[System.Windows.Forms.DialogResult]::OK; $dialog.Close() })
    if($dialog.ShowDialog($script:Window) -ne [System.Windows.Forms.DialogResult]::OK) { return }
    if(!$input.Text.Trim() -or $input.Text -eq $item.name) { return }
    [void](Invoke-NeonJson '/api/rename' @{path=$item.path;name=$input.Text.Trim()})
    Refresh-Current
}
function Delete-Selected {
    $selected=@(Get-SelectedItems)
    if(!$selected.Count) { throw 'Select file(s) or folder(s) to delete.' }
    $answer=[System.Windows.Forms.MessageBox]::Show($script:Window,
        "Permanently delete $($selected.Count) selected item(s) on the Raspberry Pi?`nFolders include all contents. This cannot be undone.",
        'Delete Pi files?', [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Warning, [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
    if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    [void](Invoke-NeonJson '/api/delete' @{paths=@($selected | ForEach-Object {$_.path});confirm=$true})
    Refresh-Current
}
function Open-Selected {
    if ($script:Files.SelectedItems.Count -gt 0) { $item=$script:Files.SelectedItems[0].Tag }
    else { $selected=@(Get-SelectedItems); if($selected.Count -ne 1){return}; $item=$selected[0] }
    if($item.type -eq 'directory') { Navigate-To ([string]$item.path) }
    else { Download-One $item }
}
function Run-Safely([scriptblock]$action) {
    try { & $action } catch { Show-Error $_.Exception.Message }
}

$backButton.Add_Click({Run-Safely {if($script:HistoryIndex -gt 0){$script:HistoryIndex--; Navigate-To $script:History[$script:HistoryIndex] $true}}})
$upButton.Add_Click({Run-Safely {Navigate-To (Parent-Path $script:Path)}})
$homeButton.Add_Click({Run-Safely {Navigate-To ''}})
$refreshButton.Add_Click({Run-Safely {Refresh-Current}})
$goButton.Add_Click({Run-Safely {Navigate-To $pathBox.Text}})
$pathBox.Add_KeyDown({param($s,$e) if($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter){$e.SuppressKeyPress=$true;Run-Safely {Navigate-To $pathBox.Text}}})
$script:Search.Add_TextChanged({Draw-Items})
$script:Files.Add_ColumnClick({param($s,$e)
    if($script:SortColumn -eq $e.Column) {$script:SortDescending=!$script:SortDescending}
    else {$script:SortColumn=$e.Column; $script:SortDescending=$false}
    Draw-Items
})
$script:Files.Add_DoubleClick({Run-Safely {Open-Selected}})
$downloadButton.Add_Click({Run-Safely {Download-CurrentSelection}})
$zipButton.Add_Click({Run-Safely {Download-Zip (Get-SelectedItems)}})
$selectButton.Add_Click({foreach($row in $script:Files.Items){$row.Checked=$true}})
$clearButton.Add_Click({foreach($row in $script:Files.Items){$row.Checked=$false;$row.Selected=$false}})
$newFolderButton.Add_Click({Run-Safely {New-Folder}})
$renameButton.Add_Click({Run-Safely {Rename-Selected}})
$deleteButton.Add_Click({Run-Safely {Delete-Selected}})
$webButton.Add_Click({Run-Safely {
    $launcher=Join-Path $PSScriptRoot 'neon-client.bat'
    if(!(Test-Path -LiteralPath $launcher)){throw 'Missing neon-client.bat next to this file.'}
    Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c',('"'+$launcher+'" -Opera'))
}})
$script:Tree.Add_BeforeExpand({param($s,$e)
    Run-Safely {Populate-TreeNode $e.Node}
})
$script:Tree.Add_AfterSelect({param($s,$e)
    if($null -ne $e.Node -and $null -ne $e.Node.Tag) {
        $requested=[string]$e.Node.Tag
        if($requested -ne $script:Path){Run-Safely {Navigate-To $requested}}
    }
})
$script:Files.Add_MouseDown({param($s,$e)
    if($e.Button -eq [System.Windows.Forms.MouseButtons]::Right) {
        $row=$script:Files.GetItemAt($e.X,$e.Y)
        if($null -ne $row -and !$row.Selected) {
            foreach($r in $script:Files.SelectedItems){$r.Selected=$false}
            $row.Selected=$true
        }
    }
})
$menu=New-Object System.Windows.Forms.ContextMenuStrip
$menuOpen=$menu.Items.Add('Open folder / Download file'); $menuOpen.Add_Click({Run-Safely {Open-Selected}})
$menuZip=$menu.Items.Add('Download as ZIP'); $menuZip.Add_Click({Run-Safely {Download-Zip (Get-SelectedItems)}})
[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))
$menuRename=$menu.Items.Add('Rename'); $menuRename.Add_Click({Run-Safely {Rename-Selected}})
$menuDelete=$menu.Items.Add('Delete permanently'); $menuDelete.Add_Click({Run-Safely {Delete-Selected}})
$script:Files.ContextMenuStrip=$menu

try {
    Navigate-To ''
    $rootNode=Create-TreeNode 'Share' '' $true
    [void]$script:Tree.Nodes.Add($rootNode)
    Populate-TreeNode $rootNode
    $rootNode.Expand()
    if ($script:SharePath -match '[/\\]uploads$' -and $script:Items.Count -eq 0) {
        [void][System.Windows.Forms.MessageBox]::Show($script:Window,
            'The Pi currently points at an empty uploads directory, not necessarily your existing share.' + "`n" +
            'On the Pi, restart with: python3 run.py --host 0.0.0.0 --port 8080 --share-root /actual/share/path',
            'Check configured Pi share', [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning)
    }
} catch {
    Show-Error ('Cannot browse the Pi share: '+$_.Exception.Message + "`n" +
        'Confirm the Pi is running the latest server, reachable over LAN, and its share root exists.')
    exit 1
}
$script:Window.Add_Shown({
    try { $split.Panel1MinSize=130; $split.Panel2MinSize=330; $split.SplitterDistance=260 } catch {}
})
[void]$script:Window.ShowDialog()
