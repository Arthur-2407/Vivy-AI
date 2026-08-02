using UnityEngine;

public class ProceduralDance : MonoBehaviour
{
    public Transform hips;
    public Transform spine;
    public Transform chest;
    public Transform leftArm;
    public Transform rightArm;
    public Transform head;

    public float bpm = 120f;
    public float hipSwing = 10f;
    public float armSwing = 35f;
    public float spineBend = 6f;
    public float headTilt = 5f;

    Quaternion hipsStart;
    Quaternion spineStart;
    Quaternion chestStart;
    Quaternion leftArmStart;
    Quaternion rightArmStart;
    Quaternion headStart;

    void Start()
    {
        hipsStart = hips.localRotation;
        spineStart = spine.localRotation;
        chestStart = chest.localRotation;
        leftArmStart = leftArm.localRotation;
        rightArmStart = rightArm.localRotation;
        headStart = head.localRotation;
    }

    void LateUpdate()
    {
        float t = Time.time * bpm / 60f;
        float beat = Mathf.Sin(t * Mathf.PI * 2f);

        hips.localRotation =
            hipsStart *
            Quaternion.Euler(0f, beat * hipSwing, 0f);

        spine.localRotation =
            spineStart *
            Quaternion.Euler(beat * spineBend, 0f, 0f);

        chest.localRotation =
            chestStart *
            Quaternion.Euler(0f, 0f, beat * 4f);

        leftArm.localRotation =
            leftArmStart *
            Quaternion.Euler(beat * armSwing, 0f, 0f);

        rightArm.localRotation =
            rightArmStart *
            Quaternion.Euler(-beat * armSwing, 0f, 0f);

        head.localRotation =
            headStart *
            Quaternion.Euler(0f, beat * headTilt, 0f);
    }
}