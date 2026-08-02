using UnityEditor;
using UnityEngine;
using VivyAI.Editor;

[InitializeOnLoad]
public class AutoFixRunner
{
    static AutoFixRunner()
    {
        EditorApplication.delayCall += RunFix;
    }

    static void RunFix()
    {
        if (SessionState.GetBool("AutoFixRun15", false)) return;
        SessionState.SetBool("AutoFixRun15", true);

        Debug.Log("[AutoFixRunner] Triggering Forensic Audit...");

        // Ensure the class exists before calling
        ForensicAuditRunner.RunAudit();

        Debug.Log("[AutoFixRunner] Done!");
    }
}
