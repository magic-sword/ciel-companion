// 会話画面の UI の画像（Assets/Resources/CielUI。scripts/ui/make_ui_sprites.py が作る）の取り込みの設定。
// 形とアイコンは圧縮せず、丸（circle・circle_outline）は角丸の板やカプセルにも使えるよう、9 分割の境界を付ける。
// 背景は縮小用の段階（ミップマップ）なしで、ふつうの圧縮にする。
using UnityEditor;
using UnityEngine;

namespace Ciel.EditorTools
{
    public sealed class CielUIImport : AssetPostprocessor
    {
        const string Folder = "Assets/Resources/CielUI/";

        void OnPreprocessTexture()
        {
            if (!assetPath.StartsWith(Folder)) return;
            var ti = (TextureImporter)assetImporter;
            ti.textureType = TextureImporterType.Sprite;
            ti.spriteImportMode = SpriteImportMode.Single;
            ti.mipmapEnabled = false;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.filterMode = FilterMode.Bilinear;
            ti.alphaIsTransparency = true;
            ti.sRGBTexture = true;
            if (assetPath.StartsWith(Folder + "Backgrounds/"))
            {
                ti.maxTextureSize = 2048;
                ti.textureCompression = TextureImporterCompression.Compressed;
                return;
            }
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            var name = System.IO.Path.GetFileNameWithoutExtension(assetPath);
            if (name == "circle" || name == "circle_outline")
                ti.spriteBorder = new Vector4(63, 63, 63, 63);
        }
    }
}
