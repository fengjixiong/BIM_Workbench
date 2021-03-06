# -*- coding: utf-8 -*-

#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2018 Yorik van Havre <yorik@uncreated.net>              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

"""This module contains FreeCAD commands for the BIM workbench"""

import os,FreeCAD,FreeCADGui,Arch_rc
from PySide import QtCore,QtGui


def QT_TRANSLATE_NOOP(ctx,txt): return txt # dummy function for the QT translator

qprops = ["Length","Width","Height","Area","HorizontalArea","VerticalArea","Volume"]

class BIM_IfcElements:


    def GetResources(self):

        return {'Pixmap'  : os.path.join(os.path.dirname(__file__),"icons","BIM_IfcElements.svg"),
                'MenuText': QT_TRANSLATE_NOOP("BIM_IfcElements", "Manage IFC elements..."),
                'ToolTip' : QT_TRANSLATE_NOOP("BIM_IfcElements", "Manage how the different elements of of your BIM project will be exported to IFC")}

    def IsActive(self):

        if FreeCAD.ActiveDocument:
            # disable for pre-v0.18
            if float(FreeCAD.Version()[0]+"."+FreeCAD.Version()[1]) < 0.18:
                return False
            return True
        else:
            return False

    def Activated(self):

        # build objects list
        self.objectslist = {}
        for obj in FreeCAD.ActiveDocument.Objects:
            if hasattr(obj,"IfcRole"):
                mat = ""
                if hasattr(obj,"Material") and obj.Material:
                    mat = obj.Material.Name
                self.objectslist[obj.Name] = [obj.IfcRole,mat]
        import ArchComponent
        self.ifcroles = ArchComponent.IfcRoles

        # load the form and set the tree model up
        self.form = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__),"dialogIfcElements.ui"))
        self.form.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__),"icons","BIM_IfcElements.svg")))
        self.model = QtGui.QStandardItemModel()
        self.form.tree.setModel(self.model)
        self.form.tree.setUniformRowHeights(True)
        self.form.tree.setItemDelegate(IfcElementsDelegate(dialog=self))
        self.form.globalMode.addItems([" "]+self.ifcroles)
        self.form.groupMode.setItemIcon(2,QtGui.QIcon(":/icons/Arch_Material.svg"))
        self.form.groupMode.setItemIcon(3,QtGui.QIcon(":/icons/Document.svg"))
        self.form.buttonEdit.setIcon(QtGui.QIcon(":/icons/IFC.svg"))
        self.form.globalMaterial.addItem(" ")
        self.materials = []
        for o in FreeCAD.ActiveDocument.Objects:
            if o.isDerivedFrom("App::MaterialObject"):
                self.materials.append(o.Name)
                self.form.globalMaterial.addItem(o.Label)
        QtCore.QObject.connect(self.form.groupMode, QtCore.SIGNAL("currentIndexChanged(int)"), self.update)
        QtCore.QObject.connect(self.form.tree, QtCore.SIGNAL("clicked(QModelIndex)"), self.setGlobalMode)
        QtCore.QObject.connect(self.form.onlyVisible, QtCore.SIGNAL("stateChanged(int)"), self.update)
        QtCore.QObject.connect(self.form.buttonBox, QtCore.SIGNAL("accepted()"), self.accept)
        QtCore.QObject.connect(self.form.globalMode, QtCore.SIGNAL("currentIndexChanged(int)"), self.getGlobalMode)
        QtCore.QObject.connect(self.form.globalMaterial, QtCore.SIGNAL("currentIndexChanged(int)"), self.getGlobalMaterial)
        QtCore.QObject.connect(self.form.buttonEdit, QtCore.SIGNAL("clicked()"), self.editProperties)

        # quantities tab
        self.qmodel = QtGui.QStandardItemModel()
        self.form.quantities.setModel(self.qmodel)
        self.form.quantities.setUniformRowHeights(True)
        self.form.quantities.setItemDelegate(QtGui.QStyledItemDelegate())
        self.quantitiesDrawn = False
        QtCore.QObject.connect(self.qmodel, QtCore.SIGNAL("dataChanged(QModelIndex,QModelIndex)"), self.setChecked)

        # center the dialog over FreeCAD window
        mw = FreeCADGui.getMainWindow()
        self.form.move(mw.frameGeometry().topLeft() + mw.rect().center() - self.form.rect().center())

        self.update()
        self.form.show()

    def update(self,index=None):

        import Draft

        # store current state of tree into self.objectslist before redrawing
        for row in range(self.model.rowCount()):
            name = self.model.item(row,0).toolTip()
            mat = self.model.item(row,2).toolTip()
            if name:
                self.objectslist[name] = [self.model.item(row,1).text(),mat]
            if self.model.item(row,0).hasChildren():
                for childrow in range(self.model.item(row,0).rowCount()):
                    name = self.model.item(row,0).child(childrow,0).toolTip()
                    mat = self.model.item(row,0).child(childrow,2).toolTip()
                    if name:
                        self.objectslist[name] = [self.model.item(row,0).child(childrow,1).text(),mat]
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["Label","IFC type","Material"])
        #self.form.tree.header().setResizeMode(QtGui.QHeaderView.Stretch)
        #self.form.tree.resizeColumnsToContents()

        # quantities tab - only fill once
        if not self.quantitiesDrawn:
            self.qmodel.setHorizontalHeaderLabels(["Label","Length","Width","Height","Area","Horiz Area","Vert Area","Volume"])

            # sort by type
            groups = {}
            for name,rolemat in self.objectslist.items():
                role = rolemat[0]
                groups.setdefault(role,[]).append(name)
            for names in groups.values():
                for name in names:
                    obj = FreeCAD.ActiveDocument.getObject(name)
                    if obj:
                        if (not self.form.onlyVisible.isChecked()) or obj.ViewObject.isVisible():
                            if obj.isDerivedFrom("Part::Feature") and not (Draft.getType(obj) == "Site"):
                                it1 = QtGui.QStandardItem(obj.Label)
                                it1.setToolTip(name)
                                it1.setEditable(False)
                                if QtCore.QFileInfo(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg").exists():
                                    icon = QtGui.QIcon(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg")
                                else:
                                    icon = QtGui.QIcon(":/icons/Arch_Component.svg")
                                it1.setIcon(icon)
                                props = []
                                for prop in qprops:
                                    it = QtGui.QStandardItem()
                                    val = None
                                    if prop == "Volume":
                                        if obj.Shape and hasattr(obj.Shape,"Volume"):
                                            val = FreeCAD.Units.Quantity(obj.Shape.Volume,FreeCAD.Units.Volume)
                                            it.setText(val.getUserPreferred()[0].replace(u"^3",u"³"))
                                            it.setCheckable(True)
                                    else:
                                        if hasattr(obj,prop) and (not "Hidden" in obj.getEditorMode(prop)):
                                            val = getattr(obj,prop)
                                            it.setText(val.getUserPreferred()[0].replace(u"^2",u"²"))
                                            it.setCheckable(True)
                                    if val != None:
                                        if hasattr(obj,"IfcAttributes") and ("Export"+prop in obj.IfcAttributes) and obj.IfcAttributes["Export"+prop]:
                                            it.setCheckState(True)
                                        if val == 0:
                                            it.setIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__),"icons","warning.svg")))
                                    if prop in ["Area","HorizontalArea","VerticalArea","Volume"]:
                                        it.setEditable(False)
                                    props.append(it)
                                self.qmodel.appendRow([it1]+props)
            self.quantitiesDrawn = True

        if self.form.groupMode.currentIndex() == 1: # group by type

            groups = {}
            for name,rolemat in self.objectslist.items():
                role = rolemat[0]
                mat = rolemat[1]
                obj = FreeCAD.ActiveDocument.getObject(name)
                if obj:
                    if (not self.form.onlyVisible.isChecked()) or obj.ViewObject.isVisible():
                        groups.setdefault(role,[]).append([name,mat])

            for group in groups.keys():
                s1 = group + " ("+str(len(groups[group]))+")"
                top = QtGui.QStandardItem(s1)
                self.model.appendRow([top,QtGui.QStandardItem(),QtGui.QStandardItem()])
                for name,mat in groups[group]:
                    obj = FreeCAD.ActiveDocument.getObject(name)
                    if obj:
                        it1 = QtGui.QStandardItem(obj.Label)
                        if QtCore.QFileInfo(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg").exists():
                            icon = QtGui.QIcon(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg")
                        else:
                            icon = QtGui.QIcon(":/icons/Arch_Component.svg")
                        it1.setIcon(icon)
                        it1.setToolTip(obj.Name)
                        it2 = QtGui.QStandardItem(group)
                        if group != obj.IfcRole:
                            it2.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                        matlabel = ""
                        if mat:
                            matobj = FreeCAD.ActiveDocument.getObject(mat)
                            if matobj:
                                matlabel = matobj.Label
                        it3 = QtGui.QStandardItem(matlabel)
                        it3.setToolTip(mat)
                        omat = ""
                        if hasattr(obj,"Material") and obj.Material:
                            omat = obj.Material.Name
                            if omat != mat:
                                it3.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                        top.appendRow([it1,it2,it3])
                top.sortChildren(0)
            self.form.tree.expandAll()

            # span top levels
            if self.form.groupMode.currentIndex() in [1,2]:
                idx = self.model.invisibleRootItem().index()
                for i in range(self.model.rowCount()):
                    if self.model.item(i,0).hasChildren():
                        self.form.tree.setFirstColumnSpanned(i, idx, True)

        elif self.form.groupMode.currentIndex() == 2: # group by material

            groups = {}
            for name,rolemat in self.objectslist.items():
                role = rolemat[0]
                mat = rolemat[1]
                if not mat:
                    mat = "Undefined"
                obj = FreeCAD.ActiveDocument.getObject(name)
                if obj:
                    if (not self.form.onlyVisible.isChecked()) or obj.ViewObject.isVisible():
                        groups.setdefault(mat,[]).append([name,role])

            for group in groups.keys():
                grlabel = "Undefined"
                if group != "Undefined":
                    matobj = FreeCAD.ActiveDocument.getObject(group)
                    if matobj:
                        grlabel = matobj.Label
                s1 = grlabel + " ("+str(len(groups[group]))+")"
                top = QtGui.QStandardItem(s1)
                self.model.appendRow([top,QtGui.QStandardItem(),QtGui.QStandardItem()])
                for name,role in groups[group]:
                    obj = FreeCAD.ActiveDocument.getObject(name)
                    if obj:
                        it1 = QtGui.QStandardItem(obj.Label)
                        if QtCore.QFileInfo(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg").exists():
                            icon = QtGui.QIcon(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg")
                        else:
                            icon = QtGui.QIcon(":/icons/Arch_Component.svg")
                        it1.setIcon(icon)
                        it1.setToolTip(obj.Name)
                        it2 = QtGui.QStandardItem(role)
                        if role != obj.IfcRole:
                            it2.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                        mat = ""
                        matlabel = ""
                        if group != "Undefined":
                            matobj = FreeCAD.ActiveDocument.getObject(group)
                            if matobj:
                                matlabel = matobj.Label
                                mat = matobj.Name
                        it3 = QtGui.QStandardItem(matlabel)
                        it3.setToolTip(mat)
                        omat = ""
                        if hasattr(obj,"Material") and obj.Material:
                            omat = obj.Material.Name
                            if omat != mat:
                                it3.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                        top.appendRow([it1,it2,it3])
                top.sortChildren(0)
            self.form.tree.expandAll()

            # span top levels
            if self.form.groupMode.currentIndex() in [1,2]:
                idx = self.model.invisibleRootItem().index()
                for i in range(self.model.rowCount()):
                    if self.model.item(i,0).hasChildren():
                        self.form.tree.setFirstColumnSpanned(i, idx, True)

        elif self.form.groupMode.currentIndex() == 3: # group by model structure

            # order by hierarchy
            def istop(obj):
                for parent in obj.InList:
                    if parent.Name in self.objectslist.keys():
                        return False
                return True

            rel = []
            deps = []
            for name in self.objectslist.keys():
                obj = FreeCAD.ActiveDocument.getObject(name)
                if obj:
                    if istop(obj):
                        rel.append(obj)
                    else:
                        deps.append(obj)
            pa = 1
            while deps:
                for obj in rel:
                    for child in obj.OutList:
                        if child in deps:
                            rel.append(child)
                            deps.remove(child)
                pa += 1
                if pa == 10: # max 10 hierarchy levels, okay? Let's keep civilised
                    rel.extend(deps)
                    break

            #print "rel:",[o.Label for o in rel]

            done = {}
            for obj in rel:
                rolemat = self.objectslist[obj.Name]
                role = rolemat[0]
                mat = rolemat[1]

                if (not self.form.onlyVisible.isChecked()) or obj.ViewObject.isVisible():
                    it1 = QtGui.QStandardItem(obj.Label)
                    if QtCore.QFileInfo(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg").exists():
                        icon = QtGui.QIcon(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg")
                    else:
                        icon = QtGui.QIcon(":/icons/Arch_Component.svg")
                    it1.setIcon(icon)
                    it1.setToolTip(obj.Name)
                    it2 = QtGui.QStandardItem(role)
                    if role != obj.IfcRole:
                        it2.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                    matlabel = ""
                    if mat:
                        matobj = FreeCAD.ActiveDocument.getObject(mat)
                        if matobj:
                            matlabel = matobj.Label
                    else:
                        mat = ""
                    it3 = QtGui.QStandardItem(matlabel)
                    it3.setToolTip(mat)
                    omat = ""
                    if hasattr(obj,"Material") and obj.Material:
                        omat = obj.Material.Name
                        if omat != mat:
                            it3.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                    ok = False
                    for par in obj.InList:
                        if par.Name in done:
                            done[par.Name].appendRow([it1,it2,it3])
                            done[obj.Name] = it1
                            ok = True
                            break
                    if not ok:
                        self.model.appendRow([it1,it2,it3])
                        done[obj.Name] = it1
            self.form.tree.expandAll()

        else: # alphabetic order

            for name,rolemat in self.objectslist.items():
                role = rolemat[0]
                mat = rolemat[1]
                obj = FreeCAD.ActiveDocument.getObject(name)
                if obj:
                    if (not self.form.onlyVisible.isChecked()) or obj.ViewObject.isVisible():
                        it1 = QtGui.QStandardItem(obj.Label)
                        if QtCore.QFileInfo(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg").exists():
                            icon = QtGui.QIcon(":/icons/Arch_"+obj.Proxy.Type+"_Tree.svg")
                        else:
                            icon = QtGui.QIcon(":/icons/Arch_Component.svg")
                        it1.setIcon(icon)
                        it1.setToolTip(obj.Name)
                        it2 = QtGui.QStandardItem(role)
                        if role != obj.IfcRole:
                            it2.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                        matlabel = ""
                        if mat:
                            matobj = FreeCAD.ActiveDocument.getObject(mat)
                            if matobj:
                                matlabel = matobj.Label
                        else:
                            mat = ""
                        it3 = QtGui.QStandardItem(matlabel)
                        it3.setToolTip(mat)
                        omat = ""
                        if hasattr(obj,"Material") and obj.Material:
                            omat = obj.Material.Name
                            if omat != mat:
                                it3.setIcon(QtGui.QIcon(":/icons/edit-edit.svg"))
                        self.model.appendRow([it1,it2,it3])

        self.model.sort(0)

    def setGlobalMode(self,index=None):

        FreeCADGui.Selection.clearSelection()
        sel = self.form.tree.selectedIndexes()
        mode = None
        mat = None
        for index in sel:
            if index.column() == 0:
                obj = FreeCAD.ActiveDocument.getObject(self.model.itemFromIndex(index).toolTip())
                if obj:
                    FreeCADGui.Selection.addSelection(obj)
        for index in sel:
            if index.column() == 1:
                if index.data() in self.ifcroles:
                    if mode:
                        if index.data() != mode:
                            mode = None
                            break
                    else:
                        mode = index.data()
        for index in sel:
            if index.column() == 2:
                item = self.model.itemFromIndex(index)
                m = FreeCAD.ActiveDocument.getObject(item.toolTip())
                if mat:
                    if m != mat:
                        mat = None
                        break
                else:
                    mat = m
        if mode:
            self.form.globalMode.setCurrentIndex(self.ifcroles.index(mode)+1)
        else:
            self.form.globalMode.setCurrentIndex(0)
        if mat:
            self.form.globalMaterial.setCurrentIndex(self.materials.index(mat.Name)+1)
        else:
            self.form.globalMaterial.setCurrentIndex(0)
        if len(sel) > 3:
            self.form.buttonEdit.setEnabled(False)
        else:
            self.form.buttonEdit.setEnabled(True)

    def getGlobalMode(self,index=-1):

        changed = False
        if index >= 1:
            role = self.ifcroles[index-1]
            sel = self.form.tree.selectedIndexes()
            for index in sel:
                if index.column() == 1:
                    if role:
                        if index.data() != role:
                            self.model.setData(index, role)
                            changed = True
        if changed:
            self.update()

    def getGlobalMaterial(self,index=-1):

        changed = False
        if index >= 1:
            mat = self.materials[index-1]
            sel = self.form.tree.selectedIndexes()
            for index in sel:
                if index.column() == 2:
                    if mat:
                        mobj = FreeCAD.ActiveDocument.getObject(mat)
                        if mobj:
                            item = self.model.itemFromIndex(index)
                            if item.toolTip() != mat:
                                item.setText(mobj.Label)
                                item.setToolTip(mat)
                                changed = True
        if changed:
            self.update()

    def accept(self):

        # get current state of tree

        self.form.hide()
        for row in range(self.model.rowCount()):
            name = self.model.item(row,0).toolTip()
            mat = self.model.item(row,2).toolTip()
            if name:
                self.objectslist[name] = [self.model.item(row,1).text(),mat]
            if self.model.item(row,0).hasChildren():
                for childrow in range(self.model.item(row,0).rowCount()):
                    name = self.model.item(row,0).child(childrow,0).toolTip()
                    mat = self.model.item(row,0).child(childrow,2).toolTip()
                    if name:
                        self.objectslist[name] = [self.model.item(row,0).child(childrow,1).text(),mat]
        changed = False
        for name,rolemat in self.objectslist.items():
            role = rolemat[0]
            mat = rolemat[1]
            obj = FreeCAD.ActiveDocument.getObject(name)
            if obj:
                if obj.IfcRole != role:
                    if not changed:
                        FreeCAD.ActiveDocument.openTransaction("Change IFC role")
                        changed = True
                    obj.IfcRole = role
                if mat and hasattr(obj,"Material"):
                    mobj = FreeCAD.ActiveDocument.getObject(mat)
                    if mobj:
                        if obj.Material:
                            if (obj.Material.Name != mat):
                                if not changed:
                                    FreeCAD.ActiveDocument.openTransaction("Change material")
                                    changed = True
                                obj.Material = mobj
                        else:
                            if not changed:
                                FreeCAD.ActiveDocument.openTransaction("Change material")
                                changed = True
                            obj.Material = mobj

        # quantities

        for row in range(self.qmodel.rowCount()):
            name = self.qmodel.item(row,0).toolTip()
            obj = FreeCAD.ActiveDocument.getObject(name)
            if obj:
                for i in range(0,6):
                    item = self.qmodel.item(row,i+1)
                    val = item.text()
                    sav = bool(item.checkState())
                    if i < 3:
                        if hasattr(obj,qprops[i]):
                            if getattr(obj,qprops[i]).getUserPreferred()[0] != val:
                                setattr(obj,qprops[i],val)
                                changed = True
                    if sav:
                        if hasattr(obj,"IfcAttributes"):
                            if (not "Export"+qprops[i] in obj.IfcAttributes) or (obj.IfcAttributes["Export"+qprops[i]] != sav):
                                d = obj.IfcAttributes
                                d["Export"+qprops[i]] = "True"
                                obj.IfcAttributes = d
                                changed = True
                    else:
                        if hasattr(obj,"IfcAttributes"):
                            if ("Export"+qprops[i] in obj.IfcAttributes):
                                if obj.IfcAttributes["Export"+qprops[i]] != sav:
                                    d = obj.IfcAttributes
                                    d["Export"+qprops[i]] = "False"
                                    obj.IfcAttributes = d
                                    changed = True

        if changed:
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()

    def editProperties(self):

        sel = self.form.tree.selectedIndexes()
        if len(sel) <= 3:
            obj = FreeCAD.ActiveDocument.getObject(self.model.itemFromIndex(sel[0]).toolTip())
            if obj:
                import ArchComponent
                p = ArchComponent.ComponentTaskPanel()
                p.obj = obj
                p.editIfcProperties()

    def setChecked(self,id1,id2):

        sel = self.form.quantities.selectedIndexes()
        state = self.qmodel.itemFromIndex(id1).checkState()
        if len(sel) > 7:
            for idx in sel:
                if idx.column() == id1.column():
                    item = self.qmodel.itemFromIndex(idx)
                    if item.checkState() != state:
                        item.setCheckState(state)


class IfcElementsDelegate(QtGui.QStyledItemDelegate):


    def __init__(self, parent=None, dialog=None, *args):

        import ArchComponent,Arch_rc
        self.roles = ArchComponent.IfcRoles
        self.mats = []
        self.matlabels = []
        for o in FreeCAD.ActiveDocument.Objects:
            if o.isDerivedFrom("App::MaterialObject"):
                self.mats.append(o.Name)
                self.matlabels.append(o.Label)
        self.dialog = dialog
        self.btn = QtGui.QPushButton()
        self.btn.setIcon(QtGui.QIcon(":/icons/IFC.svg"))
        self.btn.setText("")
        QtGui.QStyledItemDelegate.__init__(self, parent, *args)

    def paint(self, painter, option, index):
        # not used - ugly and fake!
        if index.column() == 3:
            self.btn.setGeometry(option.rect)
            if option.state == QtGui.QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            p = QtGui.QPixmap.grabWidget(self.btn)
            painter.drawPixmap(option.rect.x(),option.rect.y(),p)
        else:
            QtGui.QStyledItemDelegate.paint(self, painter, option, index)

    def createEditor(self,parent,option,index):

        if index.column() > 0:
            editor = QtGui.QComboBox(parent)
        else:
            editor = QtGui.QLineEdit(parent)
        return editor

    def setEditorData(self, editor, index):

        if index.column() == 1:
            idx = -1
            editor.addItems(self.roles)
            if index.data() in self.roles:
                idx = self.roles.index(index.data())
            editor.setCurrentIndex(idx)
        elif index.column() == 2:
            idx = -1
            editor.addItems(self.matlabels)
            item = index.model().itemFromIndex(index)
            if item.toolTip() in self.mats:
                idx = self.mats.index(item.toolTip())
            editor.setCurrentIndex(idx)
        else:
            editor.setText(index.data())

    def setModelData(self, editor, model, index):

        if index.column() == 1:
            if editor.currentIndex() == -1:
                model.setData(index, "")
            else:
                model.setData(index,self.roles[editor.currentIndex()])
        if index.column() == 2:
            if editor.currentIndex() > -1:
                idx = editor.currentIndex()
                item = model.itemFromIndex(index)
                item.setText(self.matlabels[idx])
                item.setToolTip(self.mats[idx])
        else:
            model.setData(index,editor.text())
            item = model.itemFromIndex(index)
            obj = FreeCAD.ActiveDocument.getObject(item.toolTip())
            if obj:
                obj.Label = editor.text()
        self.dialog.update()


FreeCADGui.addCommand('BIM_IfcElements',BIM_IfcElements())
