"""
图片套索工具 - 圈选区域去黑底/去白底，边缘羽化融合
==================================================
用法: 双击exe 或 python BlendWithMask.py [图片路径]

快捷键:
   左键拖拽 = 圈选区域 (松开自动闭合填充)
   空格     = 棋盘格预览
   K       = 黑色背景(a=180)预览
   W       = 切换去黑底/去白底
   F/D     = 增/减羽化半径
   S       = 保存
   Ctrl+Z  = 撤销
   R       = 重置蒙版
   1/2/3   = 绘制/蒙版/原图 视图
   Q/ESC   = 退出
"""

import sys, os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── 中文文本 ──
_FONT_CACHE = {}
def _load_font(size):
    for p in ["C:/Windows/Fonts/msyh.ttc","C:/Windows/Fonts/simhei.ttf","C:/Windows/Fonts/simsun.ttc",
              "/System/Library/Fonts/PingFang.ttc","/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: pass
    return None
def _get_font(size):
    if size not in _FONT_CACHE: _FONT_CACHE[size] = _load_font(size)
    return _FONT_CACHE[size]

def put_text(img, text, pos, scale=0.6, color=(0,255,0)):
    """PIL 绘制中文（带黑色描边）"""
    fs = max(int(scale*24),12)
    f = _get_font(fs)
    if f:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pi = Image.fromarray(rgb)
        d = ImageDraw.Draw(pi)
        d.text((pos[0]+1,pos[1]+1),text,font=f,fill=(0,0,0))
        d.text(pos,text,font=f,fill=color)
        img[:] = cv2.cvtColor(np.array(pi),cv2.COLOR_RGB2BGR)
    else:
        cv2.putText(img,text,pos,cv2.FONT_HERSHEY_SIMPLEX,scale,color,2)

# ── 图像处理 ──
def make_black_transparent(img):
    """黑色→透明，彩色按亮度半透明（原Blend.py效果），保留已有alpha"""
    r = img.copy()
    rgb = img[:,:,:3].astype(np.int32)
    is_black = np.all(rgb==0, axis=2)
    r[is_black] = (0,0,0,0)
    # 非黑色：alpha = 亮度(max(R,G,B))，RGB不变
    brightness = np.max(rgb, axis=2).astype(np.uint8)
    r[~is_black, 3] = brightness[~is_black]
    # 如果原图已有透明通道，取较大值
    if np.any(img[:,:,3] < 255):
        r[:,:,3] = np.maximum(r[:,:,3], img[:,:,3])
    return r

def make_white_transparent(img):
    """白色→透明，彩色保留原色，alpha=255-距离白色"""
    r = img.copy()
    dist = np.min(img[:,:,:3], axis=2).astype(np.int32)
    alpha = np.clip(255 - dist, 0, 255).astype(np.uint8)
    r[:,:,3] = alpha
    if np.any(img[:,:,3] < 255):
        r[:,:,3] = np.maximum(r[:,:,3], img[:,:,3])
    return r

def composite(orig, blend, mask_f):
    m = np.stack([mask_f,mask_f,mask_f,mask_f],2)
    return np.clip(orig.astype(np.float32)*(1-m)+blend.astype(np.float32)*m,0,255).astype(np.uint8)

def checkerboard(h,w,s=16):
    c=np.zeros((h,w,3),np.uint8)
    for y in range(0,h,s):
        for x in range(0,w,s):
            c[y:y+s,x:x+s]=(200,200,200) if ((y//s)+(x//s))%2==0 else (128,128,128)
    return c

def over_bg(rgba, bg_bgr):
    a=rgba[:,:,3:4].astype(np.float32)/255.0
    return np.clip(rgba[:,:,:3].astype(np.float32)[:,:,::-1]*a+bg_bgr.astype(np.float32)*(1-a),0,255).astype(np.uint8)

def save_png(arr, path):
    """确保保存为RGBA PNG"""
    if arr.shape[2] == 4:
        # 确保 alpha 通道有透明值
        img = Image.fromarray(arr, "RGBA")
    else:
        # 兜底：补一个全白alpha
        h,w = arr.shape[:2]
        rgba = np.zeros((h,w,4), np.uint8)
        rgba[:,:,:3] = arr[:,:,:3]
        rgba[:,:,3] = 255
        img = Image.fromarray(rgba, "RGBA")
    img.save(path, "PNG")
    # 验证
    verify = Image.open(path)
    if verify.mode == "RGBA":
        has_alpha = np.any(np.array(verify)[:,:,3] < 255)
        print(f"✓ 保存: {path}  (RGBA, 含透明: {'是' if has_alpha else '否'})")
    else:
        print(f"⚠ 保存: {path} (模式: {verify.mode})")

def main():
    # 选图
    img_path = None
    if len(sys.argv)>=2: img_path=sys.argv[1]
    else:
        try:
            import tkinter as tk; from tkinter import filedialog
            r=tk.Tk();r.withdraw();r.attributes("-topmost",True)
            img_path=filedialog.askopenfilename(title="选择图片",filetypes=[("图片","*.png *.bmp *.jpg *.jpeg *.tga")])
            r.destroy()
        except: pass
    if not img_path or not os.path.exists(img_path):
        print("未选择图片" if not img_path else f"文件不存在: {img_path}")
        input("按 Enter 退出..."); return

    out_path = os.path.splitext(img_path)[0]+"_blended.png"
    print(f"加载: {img_path}")
    img = np.array(Image.open(img_path).convert("RGBA"))
    oh, ow = img.shape[:2]; print(f"尺寸: {ow}x{oh}")

    # 预计算
    blk = make_black_transparent(img)
    wht = make_white_transparent(img)

    # 显示缩放
    s = min(1920/ow,1080/oh,1.0) if ow>1920 or oh>1080 else 1.0
    dw, dh = int(ow*s), int(oh*s)
    if s<1: print(f"缩放: {s:.2f}")

    # 状态
    mask = np.zeros((oh,ow),np.uint8)
    bg_mode=0; blend=blk; feather=40; show=0
    undo_stack=[]; MAX_UNDO=30
    pts=[]; active=False
    preview_cache=None; preview_valid=False

    # 显示版本
    disp_orig = cv2.resize(img,(dw,dh),cv2.INTER_AREA) if s<1 else img.copy()
    disp_blend = cv2.resize(blk,(dw,dh),cv2.INTER_AREA) if s<1 else blk.copy()
    cb_full = checkerboard(dh,dw,16)
    has_a = np.any(img[:,:,3]<255)
    if has_a: base_disp = over_bg(img, checkerboard(oh,ow,16))
    else: base_disp = cv2.cvtColor(img[:,:,:3],cv2.COLOR_RGB2BGR)
    base_disp_small = cv2.resize(base_disp,(dw,dh),cv2.INTER_AREA) if s<1 else base_disp.copy()
    dark_bg = np.full((dh,dw,3),70,np.uint8)

    def push_undo():
        undo_stack.append(mask.copy())
        if len(undo_stack)>MAX_UNDO: undo_stack.pop(0)

    def update_disp_blend():
        nonlocal disp_blend
        disp_blend = cv2.resize(blend,(dw,dh),cv2.INTER_AREA) if s<1 else blend.copy()

    def do_preview(bg):
        nonlocal preview_cache,preview_valid
        md = cv2.resize(mask.astype(np.float32),(dw,dh),cv2.INTER_LINEAR)
        if feather>0:
            k=min(feather*2+1,min(dw,dh)//2*2+1)
            md=cv2.GaussianBlur(md,(k,k),0)
        pr=composite(disp_orig,disp_blend,md/255.0)
        preview_cache=over_bg(pr,bg); preview_valid=True

    # 鼠标
    def mouse_cb(ev,x,y,fl,pr):
        nonlocal pts,active,preview_valid
        ix = max(0,min(int(x/s if s<1 else x),ow-1))
        iy = max(0,min(int(y/s if s<1 else y),oh-1))
        if ev==cv2.EVENT_LBUTTONDOWN:
            pts.clear(); pts.append((ix,iy)); active=True; preview_valid=False
        elif ev==cv2.EVENT_MOUSEMOVE and active:
            pts.append((ix,iy))
        elif ev==cv2.EVENT_LBUTTONUP:
            if len(pts)>=3:
                push_undo()
                cv2.fillPoly(mask,[np.array(pts,np.int32)],255)
            active=False; pts.clear()

    cv2.namedWindow("Lasso Tool"); cv2.setMouseCallback("Lasso Tool",mouse_cb)
    print("\n左键拖拽圈选  空格=预览  K=黑背景  W=黑白切换  F/D=羽化")
    print("S=保存  Ctrl+Z=撤销  R=重置  1/2/3=视图  Q=退出\n")

    while True:
        md = cv2.resize(mask.astype(np.float32),(dw,dh),cv2.INTER_LINEAR)
        ms = cv2.resize(mask,(dw,dh),cv2.INTER_NEAREST)

        if show==1:
            view = cv2.cvtColor(ms,cv2.COLOR_GRAY2BGR)
        elif show==2:
            view = base_disp_small.copy()
        elif preview_valid and preview_cache is not None:
            view = preview_cache.copy()
        else:
            view = base_disp_small.copy()
            ov = (md/255.0*0.3).clip(0,1)
            view[:,:,2]=(view[:,:,2].astype(np.float32)*(1-ov)+255*ov).clip(0,255).astype(np.uint8)
            if pts:
                pd = np.array([(int(x*s),int(y*s)) for x,y in pts])
                if len(pd)>=2: cv2.polylines(view,[pd],False,(0,255,255),3)
                if len(pd)>0: cv2.circle(view,tuple(pd[0]),6,(0,255,255),2)

        # 底部快捷键提示
        bg_l = "去白底" if bg_mode else "去黑底"
        info = f"[{bg_l}] 羽化:{feather} | 撤销:{len(undo_stack)}" if undo_stack else f"[{bg_l}] 羽化:{feather}"
        put_text(view,info,(8,dh-24),0.55,(0,255,0))

        # 右下角快捷键
        tips = "空格=预览  K=黑背景  W=去黑/白底  F/D=羽化  S=保存  Ctrl+Z=撤销  R=重置  Q=退出"
        put_text(view,tips,(8,6),0.5,(0,255,0))

        cv2.imshow("Lasso Tool",view)
        key = cv2.waitKey(10)&0xFF

        # 点 X 关闭窗口
        if cv2.getWindowProperty("Lasso Tool", cv2.WND_PROP_VISIBLE) < 1:
            break

        # ── 键盘 ──
        if key==ord('q') or key==27: break

        elif key==ord(' ') or key==ord('p') or key==ord('P'):
            do_preview(cb_full)

        elif key==ord('k') or key==ord('K'):
            do_preview(dark_bg)

        elif key==ord('w') or key==ord('W'):
            bg_mode=1-bg_mode; blend=wht if bg_mode else blk; update_disp_blend(); preview_valid=False
            print(f"切换到{'去白底' if bg_mode else '去黑底'}")

        elif key==ord('f') or key==ord('F'):
            feather=min(feather+2,100); preview_valid=False

        elif key==ord('d') or key==ord('D'):
            feather=max(feather-2,0); preview_valid=False

        elif key==26:  # Ctrl+Z
            if undo_stack: mask[:]=undo_stack.pop(); preview_valid=False

        elif key in (19, 83, 115):  # Ctrl+S(19) 或 S(83/115)，代码完全一样
            k=feather*2+1
            fm=cv2.GaussianBlur(mask.astype(np.float32),(k,k),0) if feather>0 else mask.astype(np.float32)
            save_png(composite(img, blend, fm/255.0), out_path)
            # 如果这个分支被执行了，但 Ctrl+S 还是没效果，说明 Ctrl+S 产生的不是 19/83/115
            # 可以加一行打印确认: print(f"save key={key}")

        elif key==ord('r') or key==ord('R'):
            mask.fill(0); undo_stack.clear(); preview_valid=False; print("已重置")

        elif key==ord('1'): show=0
        elif key==ord('2'): show=1
        elif key==ord('3'): show=2

    cv2.destroyAllWindows(); print("退出")

if __name__=="__main__": main()
