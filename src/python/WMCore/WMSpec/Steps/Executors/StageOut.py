#!/usr/bin/env python
"""
_Step.Executor.StageOut_

Implementation of an Executor for a StageOut step

"""

__revision__ = "$Id: StageOut.py,v 1.19 2010/05/11 16:01:59 mnorman Exp $"
__version__ = "$Revision: 1.19 $"

import os
import os.path
import logging
import signal
import string

from WMCore.WMSpec.Steps.Executor           import Executor
from WMCore.FwkJobReport.Report             import Report

import WMCore.Storage.StageOutMgr as StageOutMgr
from WMCore.Storage.StageOutError import StageOutFailure

from WMCore.WMSpec.ConfigSectionTree import nodeParent, nodeName
from WMCore.WMSpec.Steps.StepFactory import getStepTypeHelper
        
from WMCore.WMSpec.Steps.Executors.LogArchive import Alarm, alarmHandler

class StageOut(Executor):
    """
    _StageOut_

    Execute a StageOut Step

    """        

    def pre(self, emulator = None):
        """
        _pre_

        Pre execution checks

        """

        #Are we using an emulator?
        if (emulator != None):
            return emulator.emulatePre( self.step )


        
        print "Steps.Executors.StageOut.pre called"
        return None


    def execute(self, emulator = None):
        """
        _execute_


        """
        #Are we using emulators again?
        if (emulator != None):
            return emulator.emulate( self.step, self.job )


        overrides = {}
        if hasattr(self.step, 'override'):
            overrides = self.step.override.dictionary_()

        # Set wait to 15 minutes
        waitTime = overrides.get('waitTime', 900)

        # Pull out StageOutMgr Overrides
        stageOutCall = {}
        if overrides.has_key("command") and overrides.has_key("option") \
               and overrides.has_key("se-name") and overrides.has_key("lfn-prefix"):
            stageOutCall['command']    = overrides.get('command')
            stageOutCall['option']     = overrides.get('option')
            stageOutCall['se-name']    = overrides.get('se-name')
            stageOutCall['lfn-prefix'] = overrides.get('lfn-prefix')

        # naw man, this is real
        # iterate over all the incoming files
        manager = StageOutMgr.StageOutMgr(**stageOutCall)
        manager.numberOfRetries = self.step.retryCount
        manager.retryPauseTime  = self.step.retryDelay

        # We need to find a list of steps in our task
        # And eventually a list of jobReports for out steps

        # Search through steps for report files
        filesTransferred = []

        for step in self.stepSpace.taskSpace.stepSpaces():
            if step == self.stepName:
                #Don't try to parse your own report; it's not there yet
                continue
            stepLocation = os.path.join(self.stepSpace.taskSpace.location, step)
            logging.info("Beginning report processing for step %s" % (step))
            reportLocation = os.path.join(stepLocation, 'Report.pkl')
            if not os.path.isfile(reportLocation):
                logging.error("Cannot find report for step %s in space %s" % (step, stepLocation))
                continue
            # First, get everything from a file and 'unpersist' it
            stepReport = Report(step)
            stepReport.unpersist(reportLocation)
            taskID = getattr(stepReport.data, 'id', None)

            # Don't stage out files from bad steps.
            if not stepReport.stepSuccessful(step):
                continue
            
            # Okay, time to start using stuff
            # Now I'm a bit confused about this; each report should ONLY
            # Have the results of that particular step in it,
            # So getting all the files should get ONLY the files
            # for that step; or so I hope
            files = stepReport.getAllFileRefsFromStep(step = step)
            for file in files:
                if not hasattr(file, 'lfn') and hasattr(file, 'pfn'):
                    # Then we're truly hosed on this file; ignore it
                    msg = "Not a file: %s" % file
                    logging.error(msg)
                    continue
                # Support direct-to-merge
                # This requires pulling a bunch of stuff from everywhere
                # First check if it's needed
                if hasattr(self.step.output, 'minMergeSize') and hasattr(file, 'size') \
                       and not getattr(file, 'merged', False):
                    # We need both of those to continue, and we don't
                    # direct-to-merge 
                    if file.size > self.step.output.minMergeSize:
                        # Then this goes direct to merge
                        try:
                            file = self.handleLFNForMerge(file = file)
                        except:
                            stepReport.addError(self.stepName, 50011,
                                                "DirectToMergeFailure", str(ex))
                
                # Save the input PFN in case we need it
                # Undecided whether to move file.pfn to the output PFN
                file.InputPFN   = file.pfn
                fileForTransfer = {'LFN': getattr(file, 'lfn'), \
                                   'PFN': getattr(file, 'pfn'), \
                                   'SEName' : None, \
                                   'StageOutCommand': None}
                signal.signal(signal.SIGALRM, alarmHandler)
                signal.alarm(waitTime)
                try:
                    manager(fileForTransfer)
                    #Afterwards, the file should have updated info.
                    filesTransferred.append(fileForTransfer)
                    file.StageOutCommand = fileForTransfer['StageOutCommand']
                    file.location        = fileForTransfer['SEName']
                    file.OutputPFN       = fileForTransfer['PFN']
                except Alarm:
                    msg = "Indefinite hang during stageOut of logArchive"
                    logging.error(msg)
                except Exception, ex:
                    stepReport.addError(self.stepName, 1, "StageOutFailure", str(ex))
                    stepReport.setStepStatus(self.stepName, 1)
                    stepReport.persist("Report.pkl")                        
                    raise
                        
                signal.alarm(0)
                
                

            # Am DONE with report
            # Persist it
            stepReport.persist(reportLocation)

                

        #Done with all steps, and should have a list of stagedOut files in fileForTransfer
        logging.info("Transferred %i files" %(len(filesTransferred)))
        return
    


    def post(self, emulator = None):
        """
        _post_

        Post execution checkpointing

        """
        #Another emulator check
        if (emulator != None):
            return emulator.emulatePost( self.step )
        
        print "Steps.Executors.StageOut.post called"
        return None






    # Accessory methods
    def handleLFNForMerge(self, file):
        """
        _handleLFNForMerge_

        Digs up unmerged LFN out of WMStep outputModule and 
        changes the current file to match.
        """

        # First get the output module
        # Do this by finding the name in the step report
        # And then finding that module in the WMStep Helper
        outputRef = nodeParent(file)
        if not outputRef:
            logging.error("Direct to merge failed due to broken config parentage")
            return file
        outputName = nodeName(outputRef)
        if outputName.lower() == "merged":
            # Don't skip merge for merged files!
            return file
        helper     = getStepTypeHelper(self.step)
        outputMod  = helper.getOutputModule(moduleName = outputName)

        if not outputMod:
            # Then we couldn't get the output module
            logging.error("Attempt to directly merge failed " \
                          + "due to no output module %s in WMStep" %(outputName))
            return file


        # Okay, now we should have the output Module
        # Now we just need a second LFN

        newBase = getattr(outputMod, 'mergedLFNBase', None)
        oldBase = getattr(outputMod, 'lfnBase', None)

        if not lfnBase:
            logging.error("Direct to Merge failed due to no mergedLFNBase in %s" %(outputName))
            return file

        # Replace the actual LFN base
        oldLFN = getattr(file, 'lfn')
        newLFN = oldLFN.replace(oldBase, newBase)

        # Set the file attributes
        setattr(file, 'lfn', newLFN)
        setattr(file, 'merged', True)

        return file
