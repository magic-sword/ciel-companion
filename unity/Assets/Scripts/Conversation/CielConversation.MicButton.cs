// 会話（CielConversation）のうち、マウスの横ボタンでマイクを入れる・切る（Windows）。
// 配信でゲームを遊びながら解説するとき、シエルに聞かせたくない間だけマイクを切る。ゲームを抜けてマイクボタンを押すと、
// ゲームの画面がメニューになって配信に映るので、どの画面が前にあっても効くボタンにする。
// アプリが前にないときもキーの状態を読めるよう、Windows の GetAsyncKeyState を毎フレーム見る（Player 設定の runInBackground）。
// ボタンの押下はゲームにも届く。マイクラは初期設定で横ボタンを使わない。押した瞬間に 1 回だけ切り替える。
// 使うボタンは設定画面で選び、PlayerPrefs の ciel.micSideButton に覚える。
using System.Runtime.InteropServices;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        public enum MicSideButton { Off, Back, Forward }
        public static readonly string[] MicSideButtonLabels = { "使わない", "戻る", "進む" };
        const string MicSideButtonPrefKey = "ciel.micSideButton";

        /// マイクを切り替えるマウスの横ボタン（Windows だけ）
        public MicSideButton MicSideButtonChoice { get; private set; } = MicSideButton.Back;
        public static bool CanUseMicSideButton => Application.platform == RuntimePlatform.WindowsPlayer
                                                  || Application.platform == RuntimePlatform.WindowsEditor;
        bool _micSideButtonDown;

        void LoadMicSideButton()
        {
            MicSideButtonChoice = (MicSideButton)Mathf.Clamp(PlayerPrefs.GetInt(MicSideButtonPrefKey, (int)MicSideButton.Back), 0, 2);
        }

        public void SelectMicSideButton(MicSideButton choice)
        {
            MicSideButtonChoice = choice;
            PlayerPrefs.SetInt(MicSideButtonPrefKey, (int)choice);
            _micSideButtonDown = true;   // 選んだときに押していても、離すまで切り替えない
            Changed?.Invoke();
        }

        void PollMicSideButton()
        {
            if (!CanUseMicSideButton || MicSideButtonChoice == MicSideButton.Off) return;
            var down = SideButtonDown(MicSideButtonChoice);
            if (down && !_micSideButtonDown) SetMicEnabled(!MicEnabled);
            _micSideButtonDown = down;
        }

#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
        [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
        const int VkXButton1 = 0x05, VkXButton2 = 0x06;   // 戻る・進む

        static bool SideButtonDown(MicSideButton choice) =>
            (GetAsyncKeyState(choice == MicSideButton.Back ? VkXButton1 : VkXButton2) & 0x8000) != 0;
#else
        static bool SideButtonDown(MicSideButton choice) => false;
#endif
    }
}
