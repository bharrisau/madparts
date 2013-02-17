#!/usr/bin/env python
#
# (c) 2013 Joost Yervante Damad <joost@damad.be>
# License: GPL

import numpy as np
import math
import time
import traceback
import re

from PySide import QtGui, QtCore
from PySide.QtOpenGL import *

from OpenGL.GL import *
import OpenGL.arrays.vbo as vbo

import FTGL

import jydcoffee
from syntax.jydjssyntax import JSHighlighter
from syntax.jydcoffeesyntax import CoffeeHighlighter
from jydgldraw import GLDraw
import jydlibrary

import export.eagle

# settings; TODO: expose in menu and move to QSettings
gldx = 200
gldy = 200
font_file = "/usr/share/fonts/truetype/freefont/FreeMono.ttf"
key_idle = 0.5
libraries = [('Example Library', 'library')]

class MyGLWidget(QGLWidget):
    def __init__(self, parent = None):
        super(MyGLWidget, self).__init__(parent)
        self.dot_field_data = np.array(
          [[x,y] for x in range(-gldx/2, gldx/2) for y in range(-gldy/2, gldy/2)],
          dtype=np.float32)
        self.zoomfactor = 50
        self.zoom_changed = False
        self.shapes = []
        self.font = FTGL.PixmapFont(font_file)

    def initializeGL(self):
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT)
        self.dot_field_vbo = vbo.VBO(self.dot_field_data)
        self.gldraw = GLDraw(self.font, self.zoomfactor)

    def paintGL(self):
        if self.zoom_changed:
          self.gldraw.set_zoom(self.zoomfactor)
        glClear(GL_COLOR_BUFFER_BIT)
        glColor3f(0.5, 0.5, 0.5)
        self.dot_field_vbo.bind() # make this vbo the active one
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(2, GL_FLOAT, 0, self.dot_field_vbo)
        glDrawArrays(GL_POINTS, 0, gldx*gldy)

        glColor3f(1.0, 0.0, 0.0)
        glLineWidth(1)
        glBegin(GL_LINES)
        glVertex3f(-100, 0, 0)
        glVertex3f(100, 0, 0)
        glEnd()
        glBegin(GL_LINES)
        glVertex3f(0, -100, 0)
        glVertex3f(0, 100, 0)
        glEnd()
        
        if self.shapes != None: self.gldraw.draw(self.shapes)
        if self.zoom_changed:
            self.zoom_changed = False
            self.resizeGL(self.width(), self.height())

    def resizeGL(self, w, h):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # every 'zoomfactor' pixels is one mm
        mm_visible_x = float(w)/self.zoomfactor
        if mm_visible_x < 1: mm_visible_x = 1.0
        mm_visible_y = float(h)/self.zoomfactor
        if mm_visible_y < 1: mm_visible_y = 1.0
        glOrtho(-mm_visible_x/2, mm_visible_x/2, -mm_visible_y/2, mm_visible_y/2, -1, 1)
        glViewport(0, 0, w, h)

    def set_shapes(self, s):
        self.shapes = s
        self.updateGL()


class MainWin(QtGui.QMainWindow):

  def zoom(self):
      self.glw.zoomfactor = int(self.zoom_selector.text())
      self.glw.zoom_changed = True
      self.glw.updateGL()

  def compile(self):
    def _add_names(res):
      if res == None: return None
      def generate_ints():
        for i in range(1, 10000):
          yield i
      g = generate_ints()
      def _c(x):
        if 'type' in x:
          if x['type'] in ['smd', 'pad']:
            x['name'] = str(g.next())
        else:
          x['type'] = 'silk' # default type
        return x
      return [_c(x) for x in res]

    code = self.te1.toPlainText()
    try:
      result = jydcoffee.eval_coffee_footprint(code)
      self.result = _add_names(result)
      self.te2.setPlainText(str(result))
      self.glw.set_shapes(result)
      if not self.is_fresh_from_file:
        with open(self.active_file_name, "w+") as f:
          f.write(code)
    except Exception as ex:
      self.te2.setPlainText(str(ex))
      traceback.print_exc()
      
  
  def text_changed(self):
    if key_idle > 0:
      t = time.time()
      if (t - self.last_time < float(key_idle)/1000.0):
        self.timer.stop()
        self.timer.start(key_idle)
        return
      self.last_time = t
      if self.first_keypress:
        self.first_keypress = False
        self.timer.stop()
        self.timer.start(key_idle)
        return
    self.first_keypress = True
    self.compile()
    if self.is_fresh_from_file:
      self.is_fresh_from_file = False

  def generate(self):
     export.eagle.Generate()(self.result)

  def _footprint(self):
    lsplitter = QtGui.QSplitter(QtCore.Qt.Vertical)
    self.te1 = QtGui.QTextEdit()
    self.te1.setAcceptRichText(False)
    with open(self.active_file_name) as f:
        self.te1.setPlainText(f.read())
    self.highlighter1 = CoffeeHighlighter(self.te1.document())
    self.te1.textChanged.connect(self.text_changed)
    self.te2 = QtGui.QTextEdit()
    self.te2.setReadOnly(True)
    self.highlighter2 = JSHighlighter(self.te2.document())
    lsplitter.addWidget(self.te1)
    lsplitter.addWidget(self.te2)
    return lsplitter

  def _settings(self):
    return QtGui.QLabel("TODO")

  def _make_model(self):
    self.model = QtGui.QStandardItemModel()
    self.model.setColumnCount(3)
    self.model.setHorizontalHeaderLabels(['name','id','desc'])
    parentItem = self.model.invisibleRootItem()
    first = True
    for (name, directory) in libraries:
      lib = jydlibrary.Library(name, directory)
      parentItem.appendRow(lib)
      if first:
        first = False
        first_foot = lib.first_footprint()
    return first_foot

  def row_changed(self, current, previous):
    fn = current.data(jydlibrary.Path_Role)
    if fn != None and re.match('^.+\.coffee$', fn) != None:
      with open(fn) as f:
        self.te1.setPlainText(f.read())
        self.is_fresh_from_file = True
        self.active_file_name = fn
    else:
      # TODO jump back to previous ?
      pass

  def row_double_clicked(self):
    self.left_qtab.setCurrentIndex(1)

  def _tree(self):
    first_foot = self._make_model()
    tree = QtGui.QTreeView()
    tree.setModel(self.model)
    selection_model = tree.selectionModel()
    selection_model.currentRowChanged.connect(self.row_changed)
    tree.doubleClicked.connect(self.row_double_clicked)
    first_foot.select(selection_model)
    self.active_file_name = first_foot.path
    self.tree = tree
    self.is_fresh_from_file = True
    return tree

  def _left_part(self):
    lqtab = QtGui.QTabWidget()
    lqtab.addTab(self._tree(), "library")
    lqtab.addTab(self._footprint(), "footprint")
    lqtab.addTab(self._settings(), "settings")
    lqtab.setCurrentIndex(1)
    self.left_qtab = lqtab
    return lqtab

  def _right_part(self):
    rvbox = QtGui.QVBoxLayout()
    rhbox = QtGui.QHBoxLayout()
    self.glw = MyGLWidget()
    self.zoom_selector = QtGui.QLineEdit(str(self.glw.zoomfactor))
    self.zoom_selector.setValidator(QtGui.QIntValidator(1, 250))
    self.zoom_selector.editingFinished.connect(self.zoom)
    self.zoom_selector.returnPressed.connect(self.zoom)
    rhbox.addWidget(QtGui.QLabel("Zoom: "))
    rhbox.addWidget(self.zoom_selector)
    rvbox.addLayout(rhbox)
    rvbox.addWidget(self.glw)

    right = QtGui.QWidget()
    right.setLayout(rvbox)
    return right

  def about(self):
    a = """
<p align="center"><b>madparts</b><br/>the functional footprint editor</p>
<p align="center">(c) 2013 Joost Yervante Damad &lt;joost@damad.be&gt;</p>
<p align="center"><a href="http://madparts.org">madparts.org</a></p>
"""
    QtGui.QMessageBox.about(self, "about madparts", a)
  
  def __init__(self):
    super(MainWin, self).__init__()

    splitter = QtGui.QSplitter(self, QtCore.Qt.Horizontal)
    splitter.addWidget(self._left_part())
    splitter.addWidget(self._right_part())
    self.setCentralWidget(splitter)

    self.statusBar().showMessage("Ready.")

    menuBar = self.menuBar()
    fileMenu = menuBar.addMenu('&File')
    exitAction = QtGui.QAction('Quit', self)
    exitAction.setShortcut('Ctrl+Q')
    exitAction.setStatusTip('Exit application')
    exitAction.triggered.connect(self.close)
    fileMenu.addAction(exitAction)

    footprintMenu = menuBar.addMenu('&Footprint')
    cloneAction = QtGui.QAction('&Clone', self)
    cloneAction.setDisabled(True)
    footprintMenu.addAction(cloneAction)
    removeAction = QtGui.QAction('&Remove', self)
    removeAction.setDisabled(True)
    footprintMenu.addAction(removeAction)
    eagleAction = QtGui.QAction('Export to &Eagle', self)
    eagleAction.setShortcut('Ctrl+E')
    eagleAction.setStatusTip('Generate Eagle CAD library')
    eagleAction.triggered.connect(self.generate)
    footprintMenu.addAction(eagleAction)
    kicadAction = QtGui.QAction('Export to &Kicad', self)
    kicadAction.setShortcut('Ctrl+K')
    kicadAction.setStatusTip('Generate KiCad library')
    kicadAction.setDisabled(True)
    footprintMenu.addAction(kicadAction)


    libraryMenu = menuBar.addMenu('&Library')
    createAction = QtGui.QAction('&Create', self)
    createAction.setDisabled(True)
    disconnectAction = QtGui.QAction('&Disconnect', self)
    disconnectAction.setDisabled(True)
    libraryMenu.addAction(createAction)
    libraryMenu.addAction(disconnectAction)

    helpMenu = menuBar.addMenu('&Help')
    aboutAction = QtGui.QAction("&About", self)
    aboutAction.triggered.connect(self.about)
    helpMenu.addAction(aboutAction)

    self.last_time = time.time() - 10.0
    self.first_keypress = False
    self.timer = QtCore.QTimer()
    self.timer.setSingleShot(True)
    self.timer.timeout.connect(self.text_changed)
    self.result = ""

    def close(self):
        QtGui.qApp.quit()
    
if __name__ == '__main__':
    app = QtGui.QApplication(["madparts"])
    widget = MainWin()
    widget.show()
    app.exec_()
