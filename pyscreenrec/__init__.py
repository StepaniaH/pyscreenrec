from multiprocessing import Queue, Process, Value
import os
import time
from uuid import uuid4
from warnings import warn

import cv2
import mss.screenshot
import mss
import mss.tools
import numpy as np


class ScreenRecordingInProgress(Warning):
    """
    This warning is raised when the `start_recording` or `resume_recording` methods
    are called upon a `ScreenRecorder` instance which is already running.
    """

    pass


class NoScreenRecordingInProgress(Warning):
    """
    This warning is raised when the `stop_recording` or `pause_recording` methods
    are called upon a `ScreenRecorder` instance which is not running.
    """

    pass


class NoScreenshotFoundError(Exception):
    """
    This exception is raised when pyscreenrec doesn't find any screenshots
    to make a video out of. It usually means that the `stop_recording` method
    was called too soon after the `start_recording` method was called.
    """


# todo region of the screen
# todo multiple saver processes
# todo consider writing to the video stream directly
# todo update docs


# todo BUG the process doesn't exit


class ScreenRecorder:
    """
    Base class for screen recording.
    """

    def __init__(self) -> None:
        """
        Constructor.
        """
        # 0 -> False, 1 -> True
        self.__running = Value("i", 0)
        self.screenshot_folder = os.path.join(
            os.path.expanduser("~"), ".pyscreenrec_data", str(uuid4())
        )
        os.makedirs(self.screenshot_folder, exist_ok=True)

        # clearing all the previous data if last session ended unsuccessfully
        self._clear_data()

        self.queue: Queue[mss.screenshot.ScreenShot | None] = Queue()
        self.saver_process = None

    def __getstate__(self) -> object:
        # To solve issue in python 3.9.6 of multiprocessing.Process
        # instances are unserializable, raised upon calling resume_recording
        # capture what is normally pickled
        state = self.__dict__.copy()

        # remove unpicklable/problematic variables
        # (multiprocessing.Process in this case)
        state["saver_process"] = None
        return state

    def _start_recording(self) -> None:
        """
        (Protected) Starts screen recording.

        @params

        video_name (str) --> The name of the screen recording video.

        fps (int) --> The Frames Per Second for the screen recording. Implies how much screenshots will be taken in a second.
        """
        # ! not instantiating this in the constructor because mss has issues
        # ! with using instances from main thread in sub-threads
        # ! AttributeError: '_thread._local' object has no attribute 'srcdc'
        with mss.mss() as sct:
            mon = sct.monitors[0]

            # checking if screen is already being recorded
            if self.__running.value != 0:
                warn("Screen recording is already running.", ScreenRecordingInProgress)

            else:
                self.__running.value = 1

                while self.__running.value != 0:
                    # not sleeping for exactly 1/self.fps seconds because
                    # otherwise time is lost in sleeping which could be used in
                    # capturing frames
                    # since due to thread context-switching, this screenshotter
                    # thread doesn't get all the time that it needs
                    # thus, if more than required time has been spent just on
                    # screenshotting, don't sleep at all
                    st_start = time.perf_counter()
                    self.queue.put(sct.grab(mon))
                    st_total = time.perf_counter() - st_start
                    time.sleep(max(0, 1 / self.fps - st_total))

        print("_start_recording stopped")

    def _save_image(self):
        # output = os.path.join(self.screenshot_folder, "s{}.png")
        with mss.mss() as sct:
            mon = sct.monitors[0]
            width, height = mon["width"], mon["height"]
        video = cv2.VideoWriter(
            self.video_name, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height)
        )

        while True:
            img = self.queue.get()
            if img is None:
                break

            video.write(np.asarray(img))
            # mss.tools.to_png(img.rgb, img.size, output=output.format(self.__count))
            # self.__count += 1
        print("rendering video")
        # todo remove this if redundant
        cv2.destroyAllWindows()
        video.release()
        print("rendering finished")

    def start_recording(self, video_name: str, fps: int) -> None:
        """
        Starts screen recording.

        @params

        video_name (str) --> The name of the output screen recording.

        fps (int) --> The Frames Per Second for the screen recording. Implies how much screenshots will be taken in a second.
        """
        self.fps = fps
        self.video_name = video_name

        # checking for video extension
        if not self.video_name.endswith(".mp4"):
            raise ValueError("The video's extension can only be '.mp4'.")

        Process(target=self._start_recording).start()
        if self.saver_process is None:
            self.saver_process = Process(target=self._save_image)
            self.saver_process.start()

    def stop_recording(self) -> None:
        """
        Stops screen recording.

        Raises `NoScreenshotFoundError` if no screenshots were captured.
        """
        if self.__running.value == 0:
            warn(
                "No screen recording session is going on.", NoScreenRecordingInProgress
            )
            return

        # stop both the processes
        self.__running.value = 0
        # signal _save_image process to quit
        self.queue.put(None)
        # wait until saver process has finished working
        if self.saver_process is not None:
            self.saver_process.join()

        # reset screenshot count
        # self.__count = 1

        # saving the video and clearing all screenshots
        # self._save_video()
        # self._clear_data()

    def pause_recording(self) -> None:
        """
        Pauses screen recording.
        """
        if self.__running.value == 0:
            warn(
                "No screen recording session is going on.", NoScreenRecordingInProgress
            )
            return

        self.__running.value = 0

    def resume_recording(self) -> None:
        """
        Resumes screen recording.
        """
        if self.__running.value != 0:
            warn("Screen recording is already running.", ScreenRecordingInProgress)
            return

        self.start_recording(self.video_name, self.fps)

    def _save_video(self) -> None:
        """
        (Protected) Makes a video out of the screenshots.

        @params

        video_name (str) --> Name or path to the output video.
        """
        # fetching image info
        # images = natsorted(
        #     [img for img in os.listdir(self.screenshot_folder) if img.endswith(".png")]
        # )
        # if len(images) == 0:
        #     raise NoScreenshotFoundError("No screenshot found in the `~/.pyscreenrec_data` folder.")

        # print(f"{len(images)=}")
        # frame = cv2.imread(os.path.join(self.screenshot_folder, images[0]))
        # height, width, _ = frame.shape

        # making a videowriter object
        # video = cv2.VideoWriter(
        #     video_name, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height)
        # )

        # writing all the images to a video
        # for image in images:
        #     video.write(cv2.imread(os.path.join(self.screenshot_folder, image)))

        # releasing video
        # cv2.destroyAllWindows()
        # video = self.parent_pipe.recv()
        # self.video.release()

    def _clear_data(self) -> None:
        """
        (Protected) Deletes all screenshots present in the screenshot folder taken during screen recording.
        """
        # deleting all screenshots present in the screenshot directory
        for image in os.listdir(self.screenshot_folder):
            print("clear data", image)
            os.remove(os.path.join(self.screenshot_folder, image))

    def __repr__(self) -> str:
        return "pyscreenrec is a small and cross-platform python library that can be used to record screen. \nFor more info, visit https://github.com/shravanasati/pyscreenrec#readme."


if __name__ == "__main__":
    rec = ScreenRecorder()
    print("recording started")
    rec.start_recording("Recording.mp4", fps=30)
    time.sleep(5)
    print("pausing")
    rec.pause_recording()
    time.sleep(2)
    print("resuming")
    rec.resume_recording()
    time.sleep(5)
    print("recording ended")
    rec.stop_recording()
