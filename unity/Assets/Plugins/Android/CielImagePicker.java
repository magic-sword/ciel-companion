// シエルに見せる画像を、Android の標準の画面で選ぶ（CielConversation.Image.cs から呼ぶ）。docs/vision-design-ja.md。
// - Android 13 以降は「写真の選択」（MediaStore.ACTION_PICK_IMAGES）、それより前は「ファイルを選ぶ」（ACTION_GET_CONTENT）。
//   どちらもストレージの権限は要らない。
// - 結果を受けるために、画面の無い Fragment を一時的に足す（Unity 6 の GameActivity に手を入れずに済む）。
// - 選んだ画像は、ここで長い辺 MAX_SIDE に縮めて JPEG にし、アプリのキャッシュに書く。HEIC の写真や、写真の向き（EXIF）も
//   ここで整える（Unity の Texture2D.LoadImage は HEIC を読めず、向きも見ない）。
// - C# は pick を呼んでから poll を見回る：null は選んでいるところ、空の文字は取り消し・読めない、それ以外は書いたファイルの場所。
package com.ciel.companion;

import android.app.Activity;
import android.app.Fragment;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.ImageDecoder;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

public final class CielImagePicker {
    private static final String TAG = "CielImagePicker";
    private static final String FRAGMENT_TAG = "ciel-image-picker";
    private static final int REQUEST = 4201;
    private static final int MAX_SIDE = 1280;
    private static final int JPEG_QUALITY = 88;

    private static volatile boolean busy;
    private static volatile String result;

    private CielImagePicker() {}

    /** 選ぶ画面を開く。もう選んでいるところなら false */
    public static synchronized boolean pick(final Activity activity) {
        if (busy) return false;
        busy = true;
        result = null;
        activity.runOnUiThread(new Runnable() {
            @Override public void run() {
                try {
                    activity.getFragmentManager().beginTransaction().add(new PickFragment(), FRAGMENT_TAG).commitAllowingStateLoss();
                } catch (Exception e) {
                    Log.w(TAG, "cannot open the picker", e);
                    finish("");
                }
            }
        });
        return true;
    }

    /** 選んでいるところなら null。終わったら、結果を 1 回だけ返す（取り消し・読めないときは空の文字） */
    public static synchronized String poll() {
        if (busy) return null;
        String r = result == null ? "" : result;
        result = null;
        return r;
    }

    private static synchronized void finish(String path) {
        result = path;
        busy = false;
    }

    /** 画面の無い Fragment：選ぶ画面を開き、結果を受けて JPEG にする */
    public static final class PickFragment extends Fragment {
        private boolean started;

        @Override public void onCreate(Bundle state) {
            super.onCreate(state);
            if (started) return;
            started = true;
            Intent intent;
            if (Build.VERSION.SDK_INT >= 33) {
                intent = new Intent(MediaStore.ACTION_PICK_IMAGES);
            } else {
                intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.setType("image/*");
                intent.addCategory(Intent.CATEGORY_OPENABLE);
            }
            try {
                startActivityForResult(intent, REQUEST);
            } catch (Exception e) {
                Log.w(TAG, "no picker", e);
                done("");
            }
        }

        @Override public void onActivityResult(int request, int code, Intent data) {
            if (request != REQUEST) return;
            final Uri uri = code == Activity.RESULT_OK && data != null ? data.getData() : null;
            if (uri == null) {
                done("");
                return;
            }
            final Activity activity = getActivity();
            new Thread(new Runnable() {
                @Override public void run() {
                    String path = "";
                    try {
                        path = toJpeg(activity, uri);
                    } catch (Exception e) {
                        Log.w(TAG, "cannot read the picture", e);
                    }
                    final String p = path;
                    activity.runOnUiThread(new Runnable() {
                        @Override public void run() { done(p); }
                    });
                }
            }).start();
        }

        private void done(String path) {
            finish(path);
            try {
                getFragmentManager().beginTransaction().remove(this).commitAllowingStateLoss();
            } catch (Exception ignored) {
            }
        }
    }

    private static String toJpeg(Activity activity, Uri uri) throws Exception {
        Bitmap bitmap = decode(activity, uri);
        if (bitmap == null) return "";
        int w = bitmap.getWidth(), h = bitmap.getHeight();
        float scale = Math.min(1f, (float) MAX_SIDE / Math.max(w, h));
        if (scale < 1f) {
            Bitmap small = Bitmap.createScaledBitmap(bitmap, Math.max(1, Math.round(w * scale)), Math.max(1, Math.round(h * scale)), true);
            if (small != bitmap) bitmap.recycle();
            bitmap = small;
        }
        File file = new File(activity.getCacheDir(), "ciel-pick.jpg");
        FileOutputStream out = new FileOutputStream(file);
        try {
            bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out);
        } finally {
            out.close();
            bitmap.recycle();
        }
        return file.getAbsolutePath();
    }

    private static Bitmap decode(Activity activity, Uri uri) throws Exception {
        if (Build.VERSION.SDK_INT >= 28) {
            // 写真の向き（EXIF）を反映し、HEIC も読める。大きい写真は、読むときに縮める
            ImageDecoder.Source source = ImageDecoder.createSource(activity.getContentResolver(), uri);
            return ImageDecoder.decodeBitmap(source, new ImageDecoder.OnHeaderDecodedListener() {
                @Override public void onHeaderDecoded(ImageDecoder decoder, ImageDecoder.ImageInfo info, ImageDecoder.Source s) {
                    int w = info.getSize().getWidth(), h = info.getSize().getHeight();
                    float scale = Math.min(1f, (float) MAX_SIDE / Math.max(w, h));
                    if (scale < 1f) decoder.setTargetSize(Math.max(1, Math.round(w * scale)), Math.max(1, Math.round(h * scale)));
                    decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
                }
            });
        }
        // Android 8〜8.1：大きさだけ先に読み、間引いて読む（向きはそのまま）
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        InputStream in = activity.getContentResolver().openInputStream(uri);
        try { BitmapFactory.decodeStream(in, null, bounds); } finally { if (in != null) in.close(); }
        int sample = 1;
        while (Math.max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= MAX_SIDE) sample *= 2;
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inSampleSize = sample;
        in = activity.getContentResolver().openInputStream(uri);
        try { return BitmapFactory.decodeStream(in, null, options); } finally { if (in != null) in.close(); }
    }
}
