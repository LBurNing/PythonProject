from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.uix.image import Image
from kivy.uix.floatlayout import FloatLayout
from kivy.core.window import Window
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line
from kivy.config import Config
import os
import Utils

widget = None
screenWidth = 1280
screenHeight = 720

def play_animation(frames):
    animation = MyImage(source=frames[0], frames=frames)
    Clock.schedule_interval(animation.update, 0.1)
    return animation

def OnPlayAnimation(instance):
   #播放序列帧
    frames = Utils.get_files_by_suffix('D:\\测试资源\\501203切割3\\待机', '.png')
    animation = play_animation(frames)
    widget.add_widget(animation)


class MyWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = Window.size

        myLine = MyLine()
        playAnimationBtn = MyButton(text="play animation", callback=OnPlayAnimation)

        self.add_widget(myLine)
        self.add_widget(playAnimationBtn)

class MyButton(Button):
    def __init__(self, callback=None, **kwargs):
        super().__init__(**kwargs)
        # 添加自定义样式
        self.background_color = (1, 0, 0, 1)
        self.color = (1, 1, 1, 1)
        self.width = 100
        self.height = 50
        self.pos = (screenWidth-self.width, screenHeight-self.height)

        self.callback=callback
        # 添加自定义行为
        self.bind(on_press=self.callback)

class MyLine(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        with self.canvas:
            # 设置线条颜色为绿色
            Color(0, 1, 0)
            # 画水平线
            Line(points = [0, Window.height / 2, Window.width, Window.height / 2])
            # 画垂直线
            Line(points = [Window.width / 2, 0, Window.width / 2, Window.height])

class MyImage(Image):
    def __init__(self, frames, **kwargs):
        super().__init__(**kwargs)
        self.index = 0
        self.frames = frames
        self.start = False

    def update(self, dt):
        self.source = self.frames[self.index]
        self.index = (self.index + 1) % len(self.frames)
        self.size = self.texture_size

        if not self.start:
            self.start = True
            self.center = self.parent.center

    def on_touch_down(self, touch):
        # 判断是否点中了图片
        if self.collide_point(*touch.pos):
            touch.grab(self)  # 抓住图片
            self.last_pos = touch.pos  # 记录上一个位置

    def on_touch_move(self, touch):
        # 移动图片
        if touch.grab_current == self:
            dx, dy = touch.pos[0] - self.last_pos[0], touch.pos[1] - self.last_pos[1]
            self.pos = (self.pos[0] + dx, self.pos[1] + dy)
            self.last_pos = touch.pos

    def on_touch_up(self, touch):
        # 释放图片
        if touch.grab_current == self:
            touch.ungrab(self)

class MyApp(App):
    def build(self):
        return widget

if __name__ == '__main__':
    Window.size = (screenWidth, screenHeight)
    widget = MyWidget()
    MyApp().run()