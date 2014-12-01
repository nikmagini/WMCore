import time
import logging
from WMCore.Database.CMSCouch import CouchServer, Database
from WMCore.Lexicon import splitCouchServiceURL, sanitizeURL
from WMCore.Wrappers.JsonWrapper import JSONEncoder

class RequestDBReader():

    def __init__(self, couchURL, dbName = None, couchapp = "ReqMgr"):
        couchURL = sanitizeURL(couchURL)['url']
        # set the connection for local couchDB call
        self._commonInit(couchURL, dbName, couchapp)
        
    def _commonInit(self, couchURL, dbName, couchapp):
        """
        setting up comon variables for inherited class.
        inherited class should call this in their init function
        """
        if isinstance(couchURL, Database):
            self.couchDB = couchURL
            self.couchURL = self.couchDB['host']
            self.dbName = self.couchDB.name
            self.couchServer = CouchServer(self.couchURL)
        else:    
            if dbName:
                self.couchURL = couchURL
                self.dbName = dbName
            else:
                self.couchURL, self.dbName = splitCouchServiceURL(couchURL)
            self.couchServer = CouchServer(self.couchURL)
            self.couchDB = self.couchServer.connectDatabase(self.dbName, False)
        self.couchapp = couchapp
        self.defaultStale = {"stale": "update_after"}
        
    
    def setDefaultStaleOptions(self, options):
        if not options:
            options = {}  
        if not options.has_key('stale'):
            options.update(self.defaultStale)
        return options
    
    def _setNoStale(self):
        """
        Use this only for the unittest
        """        
        self.defaultStale = {}
        
    def _getCouchView(self, view, options, keys = []):
        
        options = self.setDefaultStaleOptions(options)
            
        if keys and isinstance(keys, basestring):
            keys = [keys]
        return self.couchDB.loadView(self.couchapp, view, options, keys)
    
    
    def _filterCouchInfo(self, couchInfo):
        # remove the couch specific information
        for key in ['_rev', '_attachments']:
            if  key in couchInfo:
                del couchInfo[key]
        return
    
                
    def _formatCouchData(self, data, key = "id", filterCouch = True):
        detail = False
        result = {}
        for row in data['rows']:
            if row.has_key('error'):
                continue
            if row.has_key("doc"):
                if filterCouch:
                    self._filterCouchInfo(row["doc"])
                result[row[key]] = row["doc"]
                detail = True
            else:
                result[row[key]] = None
        if detail:
            return result
        else:
            return result.keys()
            
    def _getRequestByNames(self, requestNames, detail = True):
        """
        'status': list of the status
        """
        options = {}
        options["include_docs"] = detail
        result = self.couchDB.allDocs(options, requestNames)
        return result
        
    def _getRequestByStatus(self, statusList, detail, limit, skip):
        """
        'status': list of the status
        """
        options = {}
        options["include_docs"] = detail

        if limit != None:
            options["limit"] = limit
        if skip != None:
            options["skip"] = skip
        keys = statusList
        return self._getCouchView("bystatus", options, keys)
  
    def _getAllDocsByIDs(self, ids, include_docs = True):
        """
        keys is [id, ....]
        returns document
        """
        if len(ids) == 0:
            return []
        options = {}
        options["include_docs"] =  include_docs
        result = self.couchDB.allDocs(options, ids)
        
        return result
    
    def getDBInstance(self):
        return self.couchDB
    
    
    def getRequestByNames(self, requestNames):
        if isinstance(requestNames, basestring):
            requestNames = [requestNames]
        if len(requestNames) == 0:
            return {}
        data = self._getRequestByNames(requestNames, True)

        requestInfo = self._formatCouchData(data)
        return requestInfo
    
    def getRequestByStatus(self, statusList, detail = False, limit = None, skip = None):
        
        data = self._getRequestByStatus(statusList, detail, limit, skip)
        requestInfo = self._formatCouchData(data)

        return requestInfo
    
    def getRequestByCouchView(self, view, options, keys = []):
        options.setdefault("include_docs", True)
        data = self._getCouchView(view, options, keys)
        requestInfo = self._formatCouchData(data)
        return requestInfo