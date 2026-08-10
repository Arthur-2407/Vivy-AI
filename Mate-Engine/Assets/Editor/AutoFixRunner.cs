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
        if (!EditorPrefs.GetBool("Vivy_AutoRunStartupAudits", false)) return;

        if (SessionState.GetBool("AutoFixRun15", false)) return;
        SessionState.SetBool("AutoFixRun15", true);

        Debug.Log("[AutoFixRunner] Triggering Forensic Audit...");

        // Ensure the class exists before calling
        ForensicAuditRunner.RunAudit();

        Debug.Log("[AutoFixRunner] Done!");
    }

    [MenuItem("Tools/Vivy/Audit/Toggle Auto-Run Startup Audits", false, 102)]
    public static void ToggleAutoRunStartupAudits()
    {
        bool currentState = EditorPrefs.GetBool("Vivy_AutoRunStartupAudits", false);
        EditorPrefs.SetBool("Vivy_AutoRunStartupAudits", !currentState);
        Debug.Log($"[AutoFixRunner] Auto-Run Startup Audits is now: {(!currentState ? "ENABLED" : "DISABLED")}");
    }

    [MenuItem("Tools/Vivy/Audit/Toggle Auto-Run Startup Audits", true)]
    public static bool ValidateToggleAutoRunStartupAudits()
    {
        Menu.SetChecked("Tools/Vivy/Audit/Toggle Auto-Run Startup Audits", EditorPrefs.GetBool("Vivy_AutoRunStartupAudits", false));
        return true;
    }
}
