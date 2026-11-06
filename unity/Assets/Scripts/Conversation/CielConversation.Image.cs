// 会話（CielConversation）のうち、シエルに画像を見せる（docs/vision-design-ja.md）。
// 画像を選び（Windows：WindowsFileDialog）、長い辺 MaxSide に縮めて JPEG にし、LiveKit のファイル送信（topic ciel.image）で
// 会話サーバー（server/agent/eyes.py）へ送る。受け取ったか・だめだった理由は、会話サーバーが image.state で返す。
// 送るために一時ファイルを書き、送り終えたら消す。
using System;
using System.Collections;
using System.IO;
using LiveKit;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const string ImageTopic = "ciel.image";
        const int MaxSide = 1280;          // 長い辺。会話サーバーの上限（3 MB）に十分収まり、細かい文字も読める大きさ
        const int JpegQuality = 85;
        const long MaxSourceBytes = 40_000_000;

        /// 画像を見せられるか（今は Windows だけ。つないでいるとき）
        public bool CanShareImage => WindowsFileDialog.Available && Status == State.Connected;
        /// 見せた画像の様子：sending・received・failed（と理由 ImageReason）。空なら何もしていない
        public string ImageState { get; private set; } = "";
        public string ImageReason { get; private set; } = "";
        public float ImageStateAt { get; private set; } = -1f;

        bool _sendingImage;

        /// ファイルを選んで、シエルに見せる
        public void PickAndShareImage()
        {
            if (!CanShareImage || _sendingImage) return;
            var path = WindowsFileDialog.PickImage("シエルに見せる画像を選ぶ");
            if (!string.IsNullOrEmpty(path)) StartCoroutine(ShareImage(path));
        }

        IEnumerator ShareImage(string path)
        {
            _sendingImage = true;
            SetImageState("sending");
            string temp = null;
            try
            {
                byte[] jpeg;
                try
                {
                    if (new FileInfo(path).Length > MaxSourceBytes) { SetImageState("failed", "too_large"); yield break; }
                    jpeg = ToJpeg(File.ReadAllBytes(path));
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[CielConversation] 画像を読めない: {e.Message}");
                    SetImageState("failed", "not_image");
                    yield break;
                }
                if (jpeg == null) { SetImageState("failed", "not_image"); yield break; }
                if (_room == null || Status != State.Connected) { SetImageState("failed", "not_connected"); yield break; }
                temp = Path.Combine(Application.temporaryCachePath, "ciel-share.jpg");
                File.WriteAllBytes(temp, jpeg);
                var send = _room.LocalParticipant.SendFile(temp, new StreamByteOptions
                {
                    Topic = ImageTopic,
                    MimeType = "image/jpeg",
                    Name = Path.GetFileName(path),
                });
                yield return send;
                if (send.IsError)
                {
                    Debug.LogWarning($"[CielConversation] 画像を送れない: {send.Error.Message}");
                    SetImageState("failed", "send");
                    yield break;
                }
                Debug.Log($"[CielConversation] 画像を送った（{jpeg.Length} バイト）");
                // 受け取ったかは、会話サーバーの image.state で分かる（届かなければ sending のまま。画面は数秒で消す）
            }
            finally
            {
                _sendingImage = false;
                if (temp != null)
                {
                    try { File.Delete(temp); } catch (Exception) { }
                }
            }
        }

        /// 画像を、長い辺 MaxSide 以下の JPEG にする。画像でなければ null
        static byte[] ToJpeg(byte[] source)
        {
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                if (!tex.LoadImage(source, false)) return null;
                var scale = Mathf.Min(1f, (float)MaxSide / Mathf.Max(tex.width, tex.height));
                if (scale >= 1f) return tex.EncodeToJPG(JpegQuality);
                int w = Mathf.Max(1, Mathf.RoundToInt(tex.width * scale)), h = Mathf.Max(1, Mathf.RoundToInt(tex.height * scale));
                var rt = RenderTexture.GetTemporary(w, h, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
                var previous = RenderTexture.active;
                try
                {
                    Graphics.Blit(tex, rt);
                    RenderTexture.active = rt;
                    var small = new Texture2D(w, h, TextureFormat.RGB24, false);
                    try
                    {
                        small.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                        small.Apply(false);
                        return small.EncodeToJPG(JpegQuality);
                    }
                    finally { Destroy(small); }
                }
                finally
                {
                    RenderTexture.active = previous;
                    RenderTexture.ReleaseTemporary(rt);
                }
            }
            finally { Destroy(tex); }
        }

        void OnImageState(EventJson e)
        {
            SetImageState(e.state ?? "", e.reason ?? "");
            Debug.Log($"[CielConversation] 画像：{ImageState}{(ImageReason != "" ? $"（{ImageReason}）" : "")}");
        }

        void SetImageState(string state, string reason = "")
        {
            (ImageState, ImageReason, ImageStateAt) = (state, reason, Time.unscaledTime);
            Changed?.Invoke();
        }
    }
}
