// 画面（ウィンドウ）の大きさが変わったら、シエル（Live2D）の描画をやり直す。
// Cubism SDK（R5、URP）は、再生中に画面の大きさが変わると、その 1 フレームあとからモデルを描かなくなる（PC でウィンドウの大きさを変えたとき、
// エディタの Game ビューの大きさを変えたとき）。描画の部品（CubismRenderController）をいったん止めて動かし直すと、また描かれる
// （.local/render-check の resize-*.png で確かめた。作業用の絵を手放す CubismOffscreenRenderTextureManager.Release では戻らない）。
// 大きさが変わった直後に動かし直しても、そのあとで消える。大きさが変わらなくなってから少し待って動かし直す
// （ウィンドウをドラッグしているあいだは消えたままで、離すと戻る）。SDK を書き換えず、ここで立て直す。止めるのは 1 フレームだけ。
using System.Collections;
using Live2D.Cubism.Rendering;
using UnityEngine;

namespace Ciel.Conversation
{
    public sealed class CielResizeGuard : MonoBehaviour
    {
        const float Settle = 0.3f;   // 大きさが変わらなくなってから待つ秒数

        Vector2Int _size;
        float _changedAt = -1;
        bool _restarting;

        void Start() => _size = new Vector2Int(Screen.width, Screen.height);

        void Update()
        {
            var size = new Vector2Int(Screen.width, Screen.height);
            if (size != _size)
            {
                _size = size;
                _changedAt = Time.unscaledTime;
                return;
            }
            if (_changedAt < 0 || _restarting || Time.unscaledTime - _changedAt < Settle) return;
            _changedAt = -1;
            StartCoroutine(Restart());
        }

        IEnumerator Restart()
        {
            _restarting = true;
            var controllers = new System.Collections.Generic.List<CubismRenderController>();
            foreach (var c in FindObjectsByType<CubismRenderController>())
                if (c.enabled) { c.enabled = false; controllers.Add(c); }   // もともと止めてあるものは触らない
            yield return null;
            foreach (var c in controllers)
                if (c != null) c.enabled = true;
            Debug.Log($"[CielResizeGuard] 画面の大きさが {_size.x}×{_size.y} に変わったので、シエルの描画をやり直した");
            _restarting = false;
        }
    }
}
