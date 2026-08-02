using UnityEngine;
using UnityEditor;

[CustomEditor(typeof(MEValueChanger))]
public class MEValueChangerEditor : Editor
{
    public override void OnInspectorGUI()
    {
        EditorGUILayout.HelpBox("ME Value Changer provides runtime inspection and property modification during play mode. Press F8 (or your assigned Toggle Key) in Play Mode to view the runtime GUI.", MessageType.Info);
        
        DrawDefaultInspector();

        MEValueChanger changer = (MEValueChanger)target;

        EditorGUILayout.Space(10);
        EditorGUILayout.LabelField("Editor Controls", EditorStyles.boldLabel);

        if (Application.isPlaying)
        {
            if (GUILayout.Button("Force UI Toggle in Play Mode"))
            {
                // Send simulated key event or inform user
                Debug.Log("[MEValueChanger] To toggle the GUI, press the designated hotkey during play mode or inspect runtime properties in scene.");
            }
        }
        else
        {
            EditorGUILayout.HelpBox("Runtime controls will become active once Play Mode starts.", MessageType.None);
        }
    }
}
