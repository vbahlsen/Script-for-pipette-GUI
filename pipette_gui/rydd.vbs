Dim objFSO
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Prosesser begge mappene
ProcessFolder "C:\Tecan\Filer\PJS_eksport", "C:\Tecan\Filer\PJS_eksport\complete"
ProcessFolder "C:\Tecan\Filer\Worklist", "C:\Tecan\Filer\Worklist\complete"

' Frigjør objekter
Set objFSO = Nothing

Sub ProcessFolder(sourceFolder, targetFolder)
    Dim objFolder, objFile, targetPath

    ' Sjekk om kildemappen eksisterer
    If objFSO.FolderExists(sourceFolder) Then
        ' Sjekk om målmappen eksisterer, hvis ikke opprett den
        If Not objFSO.FolderExists(targetFolder) Then
            objFSO.CreateFolder(targetFolder)
        End If

        Set objFolder = objFSO.GetFolder(sourceFolder)

        ' Gå gjennom alle filene i kildemappen
        For Each objFile In objFolder.Files
            ' Sjekk om filen er en .csv-fil
            If LCase(objFSO.GetExtensionName(objFile.Path)) = "csv" Then
                ' Sett stien til målmappen med unikt navn
                targetPath = targetFolder & "\" & GetUniqueFileName(targetFolder, objFile.Name)

                ' Flytt filen
                objFSO.MoveFile objFile.Path, targetPath
            End If
        Next
    Else
        ' Valgfritt: Logg eller vis melding hvis kilden ikke finnes
        ' WScript.Echo "Kilden " & sourceFolder & " eksisterer ikke."
    End If
End Sub

Function GetUniqueFileName(folder, fileName)
    Dim uniqueName, count, baseName, extension
    uniqueName = fileName
    count = 1
    
    extension = objFSO.GetExtensionName(fileName)
    baseName = objFSO.GetBaseName(fileName)

    ' Inntil det finnes et unikt filnavn, legg til et tall til filnavnet
    Do While objFSO.FileExists(folder & "\" & uniqueName)
        uniqueName = baseName & "_" & count & "." & extension
        count = count + 1
    Loop

    GetUniqueFileName = uniqueName
End Function
